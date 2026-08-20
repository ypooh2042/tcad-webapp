"""세션이 끝난 사용자의 산출물 정리.

로그아웃은 사용자가 눌러야 일어난다. **브라우저만 닫으면 아무 일도 없다** —
그러면 `.str` 이 그대로 남아 디스크를 먹는다(CMOS 한 번에 5MB). 세션이 만료된
사용자를 주기적으로 훑어 비운다.

산출물은 캐시라는 전제가 이 모듈의 근거다. 소스는 작업공간에 남아 있으므로
다시 로그인해 실행하면 되살아난다. 로그는 지우지 않는다 — 그건 되살아나지
않는다.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.store import SessionStore
from app.db.models import Artifact, Job
from app.jobs.cache import discard_artifacts, enforce_storage_quota

logger = logging.getLogger(__name__)


async def sweep_idle_artifacts(
    sessionmaker: async_sessionmaker,
    store: SessionStore,
    idle_timeout: timedelta,
) -> int:
    """접속 중이 아닌 사용자의 산출물을 지운다.

    Returns:
        비운 바이트 수.
    """
    now = datetime.now(UTC)
    # **관리자 세션은 만료되지 않는다**(정원·유휴 면제). 그 면제를 여기까지
    # 끌고 오면 관리자는 로그아웃하지 않는 한 영영 정리되지 않는다 — 운영에서
    # 실제로 97MB 가 그렇게 쌓였다. 청소가 물을 것은 "지금 화면을 보고 있는가"
    # 뿐이므로 역할과 무관하게 마지막 활동 시각으로 판단한다.
    active = {
        int(session.user_id)
        for session in await store.active_sessions(now, idle_timeout)
        if now - session.last_seen_at <= idle_timeout
    }

    async with sessionmaker() as db:
        # 산출물을 가진 사용자만 본다. 전체 사용자를 훑을 이유가 없다.
        owners = set(
            await db.scalars(
                select(Job.owner_id).join(Artifact, Artifact.job_id == Job.id)
            )
        )

    freed = 0
    for owner_id in owners - active:
        async with sessionmaker() as db:
            # 한 명이 실패해도 나머지는 계속 치운다.
            try:
                freed += await discard_artifacts(db, owner_id)
            except Exception:  # noqa: BLE001 - 청소가 워커를 멈추면 안 된다
                logger.warning("산출물 정리 실패: user=%s", owner_id, exc_info=True)

    if freed:
        logger.info("산출물 %d바이트 정리", freed)
    return freed


async def run_sweeper(
    sweep: Callable[[], Awaitable[int]],
    stop: asyncio.Event,
    interval: float,
) -> None:
    """중지 신호가 올 때까지 주기적으로 청소한다.

    **한 번 실패했다고 멈추지 않는다.** 청소가 서면 디스크가 계속 찬다.
    """
    while not stop.is_set():
        try:
            await sweep()
        except Exception:  # noqa: BLE001 - 다음 주기에 다시 해 본다
            logger.warning("산출물 청소 주기 실패", exc_info=True)

        # 중지 신호가 오면 주기를 기다리지 않고 곧바로 나간다.
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue


async def sweep_over_quota(sessionmaker: async_sessionmaker, quota_bytes: int) -> int:
    """사용자별 산출물 총량을 상한 아래로 되돌린다.

    **접속 여부를 보지 않는다.** 위의 유휴 청소는 세션이 끝난 사용자만 보므로,
    한 사람이 계속 접속한 채 실행하면 아무도 치우지 않는다. 잡 하나가 최대
    256MB 라 그 경로로 디스크가 찬다.

    Returns:
        비운 바이트 수.
    """
    async with sessionmaker() as db:
        owners = set(
            await db.scalars(
                select(Job.owner_id).join(Artifact, Artifact.job_id == Job.id)
            )
        )

    freed = 0
    for owner_id in owners:
        async with sessionmaker() as db:
            # 한 명이 실패해도 나머지는 계속 치운다.
            try:
                freed += await enforce_storage_quota(db, owner_id, quota_bytes)
            except Exception:  # noqa: BLE001 - 청소가 워커를 멈추면 안 된다
                logger.warning("상한 정리 실패: user=%s", owner_id, exc_info=True)
    return freed


#: 고아 판정을 미루는 시간. 작업 디렉토리는 잡 행보다 나중에 생기므로, 갓
#: 만들어진 것을 곧바로 고아로 보면 도는 잡을 지울 수 있다.
_ORPHAN_GRACE = timedelta(hours=1)


async def sweep_orphan_workdirs(
    sessionmaker: async_sessionmaker, jobs_root: Path
) -> int:
    """어느 잡도 가리키지 않는 작업 디렉토리를 지운다.

    사용자를 지우면 잡 행은 CASCADE 로 사라지지만 디스크의 디렉토리는 그대로
    남는다. 아무도 그것을 다시 찾지 않으므로 영영 쌓인다.

    Returns:
        비운 바이트 수.
    """
    root = Path(jobs_root)
    if not root.is_dir():
        return 0

    async with sessionmaker() as db:
        known = {
            workdir for (workdir,) in (await db.execute(select(Job.workdir))).all()
        }

    cutoff = datetime.now(UTC) - _ORPHAN_GRACE
    freed = 0
    for entry in root.iterdir():
        if not entry.is_dir() or str(entry) in known:
            continue
        try:
            made = datetime.fromtimestamp(entry.stat().st_mtime, UTC)
        except OSError:
            continue
        if made > cutoff:
            continue
        freed += _directory_size(entry)
        shutil.rmtree(entry, ignore_errors=True)

    if freed:
        logger.info("고아 작업디렉토리 %d바이트 정리", freed)
    return freed


def _directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total
