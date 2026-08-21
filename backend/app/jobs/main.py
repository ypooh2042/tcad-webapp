"""워커 프로세스 진입점.

    python -m app.jobs.main

API 와 별도 프로세스로 돈다. 시뮬레이션은 CPU 를 오래 붙잡으므로 웹 프로세스에
얹으면 잡 하나가 도는 동안 상태 조회조차 느려진다. 프로세스를 나눠 두면 워커만
따로 재시작하거나 멈춰 세울 수도 있다.

동시 실행 상한을 지키는 주체는 이 프로세스가 아니라 DB 다(JobQueue.claim_next).
그래서 여기서 루프를 몇 개 돌리든, 워커 프로세스를 몇 대 띄우든 전체 동시 실행
수는 설정값을 넘지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from redis.asyncio import Redis

from app.auth.policy import SessionPolicy
from app.auth.redis_store import RedisSessionStore
from app.core.config import Settings, get_settings
from app.jobs.queue import JobQueue
from app.jobs.sweeper import (
    run_sweeper,
    sweep_idle_artifacts,
    sweep_orphan_workdirs,
    sweep_over_quota,
)
from app.jobs.worker import Worker
from app.runner.sandbox import SandboxLimits

logger = logging.getLogger(__name__)

#: 종료 신호로 받아들일 시그널. SIGTERM 은 systemd 가, SIGINT 는 터미널이 보낸다.
_SHUTDOWN_SIGNALS = (signal.SIGTERM, signal.SIGINT)


class WorkerLoop(Protocol):
    async def run_forever(self, stop: asyncio.Event) -> None: ...


def build_worker(
    settings: Settings, sessionmaker: async_sessionmaker[AsyncSession] | None
) -> Worker:
    """설정 하나에서 큐와 워커를 조립한다.

    타임아웃과 동시 실행 상한이 설정에서 흘러들어오는 지점이 여기 한 곳뿐이어야,
    설정을 고쳤는데 실제 실행은 예전 값으로 도는 일이 없다.
    """
    queue = JobQueue(sessionmaker, max_concurrent=settings.max_concurrent_jobs)
    return Worker(
        queue=queue,
        sessionmaker=sessionmaker,
        jobs_root=settings.jobs_root,
        image=settings.sandbox_image,
        devsim_image=settings.devsim_image,
        structures_root=settings.structures_root,
        limits=SandboxLimits(timeout_seconds=settings.job_timeout_seconds),
    )


async def run_loops(
    worker: WorkerLoop, stop: asyncio.Event, concurrency: int
) -> None:
    """워커 루프를 concurrency 개 동시에 돌린다.

    루프 하나는 잡 하나를 끝까지 붙들고 있으므로, 루프가 하나뿐이면 상한을 4로
    잡아도 실제로는 한 번에 하나씩만 돈다. 시뮬레이션 자체는 스레드로 나가 있어
    루프들끼리 이벤트 루프를 막지 않는다.
    """
    await asyncio.gather(*(worker.run_forever(stop) for _ in range(concurrency)))


async def run_worker(settings: Settings, stop: asyncio.Event) -> None:
    """중지 신호가 올 때까지 잡을 처리한다. 엔진은 이 프로세스가 소유한다."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    worker = build_worker(settings, sessionmaker)
    # 워커는 API 와 같은 Redis 를 본다. 활성 세션을 알아야 접속 중인 사용자의
    # 결과를 지우지 않는다.
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    store = RedisSessionStore(redis)

    try:
        # 앞선 워커가 죽으면서 남긴 잡은 RUNNING 인 채로 정원을 차지한다. 치우지
        # 않으면 재시작을 거듭할수록 슬롯이 하나씩 줄어 결국 큐가 멈춘다.
        recovered = await worker.recover_stale()
        if recovered:
            logger.warning("중단된 잡 %d 건을 큐로 되돌렸습니다", recovered)

        logger.info(
            "워커 시작 (루프 %d, 이미지 %s)",
            settings.max_concurrent_jobs,
            settings.sandbox_image,
        )
        # 산출물 청소를 워커에 얹는다. 세 갈래를 한 주기에서 함께 돈다:
        #
        #   1. 유휴 사용자 — **로그아웃만으로는 부족하다.** 브라우저를 그냥
        #      닫으면 `.str` 이 그대로 남는다.
        #   2. 총량 상한 — 1번은 접속 중인 사용자를 건드리지 않으므로, 한 사람이
        #      접속한 채 계속 실행하면 아무도 치우지 않는다. 잡 하나가 최대
        #      256MB 라 그 경로로 디스크가 찬다.
        #   3. 고아 디렉토리 — 사용자를 지우면 잡 행은 CASCADE 로 사라지지만
        #      디스크의 디렉토리는 남아 아무도 다시 찾지 않는다.
        quota_bytes = settings.storage_quota_mb * 1024 * 1024

        async def sweep() -> int:
            freed = await sweep_idle_artifacts(
                sessionmaker, store, SessionPolicy().idle_timeout
            )
            freed += await sweep_over_quota(sessionmaker, quota_bytes)
            freed += await sweep_orphan_workdirs(sessionmaker, settings.jobs_root)
            return freed

        await asyncio.gather(
            run_loops(worker, stop, settings.max_concurrent_jobs),
            run_sweeper(sweep, stop, settings.artifact_sweep_seconds),
        )
    finally:
        await redis.aclose()
        await engine.dispose()
        logger.info("워커 종료")


def install_signal_handlers(loop, stop: asyncio.Event) -> None:
    """종료 신호를 중지 이벤트로 옮긴다.

    이렇게 해야 돌고 있던 시뮬레이션이 끝난 뒤에 프로세스가 내려간다. 곧바로
    죽이면 그 잡은 RUNNING 으로 남아 다음 기동 때 되돌리기를 기다려야 한다.
    """
    for sig in _SHUTDOWN_SIGNALS:
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # 시그널 핸들러를 못 다는 플랫폼(예: Windows 이벤트 루프)에서도
            # 워커 자체는 돌아야 한다. 종료는 KeyboardInterrupt 로 처리된다.
            logger.debug("%s 핸들러를 등록할 수 없습니다", sig)


async def _serve(settings: Settings) -> None:
    stop = asyncio.Event()
    install_signal_handlers(asyncio.get_running_loop(), stop)
    await run_worker(settings, stop)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5.5s [%(name)s] %(message)s",
    )
    settings = get_settings()
    settings.jobs_root.mkdir(parents=True, exist_ok=True)
    asyncio.run(_serve(settings))


if __name__ == "__main__":
    main()
