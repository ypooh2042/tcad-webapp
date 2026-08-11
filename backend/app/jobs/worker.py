"""워커 루프.

큐에서 잡을 꺼내 샌드박스에서 돌리고 결과를 기록한다. 큐(queue.py)와 실행
(runner/)을 잇는 얇은 층이며, 실패해도 루프가 멈추지 않는 것이 핵심 책임이다.

시뮬레이션은 CPU 를 오래 붙잡는 동기 작업이라 이벤트 루프에서 직접 돌리면 안
된다. 스레드로 넘겨서 상태 조회 같은 다른 요청이 막히지 않게 한다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Artifact, JobStatus, SourceRevision
from app.jobs.queue import JobQueue
from app.runner.results import SimulationResult
from app.runner.runner import run_simulation
from app.runner.sandbox import SandboxLimits

logger = logging.getLogger(__name__)

#: 큐가 비었을 때 다음 확인까지 기다리는 시간. 이 규모에서는 폴링으로 충분하고,
#: 알림 채널을 추가하면 워커가 죽었을 때 복구 경로가 하나 더 늘어난다.
_IDLE_POLL_SECONDS = 2.0

#: 죽은 워커가 남긴 잡을 되돌리는 기준. 잡 타임아웃보다 넉넉히 길어야 한다.
#: 그렇지 않으면 정상 실행 중인 잡을 빼앗아 중복 실행하게 된다.
_STALE_MULTIPLIER = 3


class Worker:
    def __init__(
        self,
        queue: JobQueue,
        sessionmaker: async_sessionmaker[AsyncSession],
        jobs_root: Path,
        image: str,
        limits: SandboxLimits | None = None,
    ) -> None:
        self.queue = queue
        self.sessionmaker = sessionmaker
        self.jobs_root = jobs_root
        self.image = image
        self.limits = limits or SandboxLimits()

    async def run_forever(self, stop: asyncio.Event) -> None:
        """중지 신호가 올 때까지 잡을 처리한다."""
        while not stop.is_set():
            processed = await self.run_once()
            if not processed:
                await self._sleep_or_stop(stop, _IDLE_POLL_SECONDS)

    async def run_once(self) -> bool:
        """잡 하나를 처리한다.

        Returns:
            처리한 잡이 있었으면 True.
        """
        job = await self.queue.claim_next()
        if job is None:
            return False

        try:
            result = await self._execute(job.id, job.workdir)
        except Exception:
            # 한 잡의 실패로 워커가 멈추면 큐 전체가 정지한다. 잡만 실패로
            # 기록하고 루프는 계속 돈다.
            logger.exception("잡 %s 실행 중 예외", job.id)
            await self.queue.mark_finished(
                job.id,
                status=JobStatus.FAILED,
                log="워커에서 예기치 못한 오류가 발생했습니다.",
                exit_code=None,
            )
            return True

        await self._record(job.id, result)
        return True

    async def recover_stale(self) -> int:
        """죽은 워커가 남긴 잡을 큐로 되돌린다. 기동 시 한 번 부른다."""
        return await self.queue.requeue_stale(
            max_runtime=timedelta(
                seconds=self.limits.timeout_seconds * _STALE_MULTIPLIER
            )
        )

    async def _execute(self, job_id: int, workdir: str) -> SimulationResult:
        source = await self._load_source(job_id)
        # CPU 를 오래 쓰는 동기 호출이라 이벤트 루프 밖으로 내보낸다.
        return await asyncio.to_thread(
            run_simulation,
            source,
            Path(workdir),
            self.image,
            self.limits,
        )

    async def _load_source(self, job_id: int) -> str:
        async with self.sessionmaker() as session:
            from app.db.models import Job

            job = await session.get(Job, job_id)
            revision = await session.get(SourceRevision, job.source_revision_id)
            return revision.source

    async def _record(self, job_id: int, result: SimulationResult) -> None:
        await self._save_artifacts(job_id, result)
        await self.queue.mark_finished(
            job_id,
            status=_status_for(result),
            log=result.log,
            exit_code=result.exit_code,
        )

    async def _save_artifacts(
        self, job_id: int, result: SimulationResult
    ) -> None:
        if not result.structure_files:
            return
        async with self.sessionmaker() as session:
            for sequence, path in enumerate(result.structure_files, start=1):
                session.add(
                    Artifact(
                        job_id=job_id,
                        filename=path.name,
                        path=str(path),
                        size_bytes=path.stat().st_size,
                        sequence=sequence,
                    )
                )
            await session.commit()

    @staticmethod
    async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
        """중지 신호가 오면 즉시 깨어난다. 종료가 폴링 주기만큼 늦어지지 않는다."""
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            pass


def _status_for(result: SimulationResult) -> JobStatus:
    """실행 결과를 잡 상태로 옮긴다.

    종료 코드로 판정하지 않는다. 시뮬레이터는 커맨드 오류가 있어도 exit 0 으로
    끝나므로, 종료 코드만 보면 실패한 잡이 성공으로 기록된다.
    """
    if result.timed_out:
        return JobStatus.TIMED_OUT
    return JobStatus.SUCCEEDED if result.succeeded else JobStatus.FAILED
