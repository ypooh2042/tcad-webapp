"""산출물 캐시 정리.

`.str` 은 캐시다 — 소스만 남아 있으면 다시 실행해서 얻을 수 있고, 실행 한 번에
5MB 씩 쌓여 디스크를 가장 많이 먹는다(CMOS 예제 기준). 그래서 세션이 끝나면
비운다.

**로그는 남긴다.** 무엇이 왜 실패했는지는 다시 실행해도 되살아나지 않는다.
**돌고 있는 잡도 건드리지 않는다.** 작업 디렉토리를 지우면 워커가 결과를 쓸
곳을 잃는다.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Artifact, Job

logger = logging.getLogger(__name__)


async def discard_artifacts(session: AsyncSession, owner_id: int) -> int:
    """이 사용자의 산출물을 지운다.

    Returns:
        비운 바이트 수.
    """
    jobs = list(
        await session.scalars(select(Job).where(Job.owner_id == owner_id))
    )
    finished = [job for job in jobs if job.status.is_terminal]
    if not finished:
        return 0

    job_ids = [job.id for job in finished]
    freed = sum(
        artifact.size_bytes
        for artifact in await session.scalars(
            select(Artifact).where(Artifact.job_id.in_(job_ids))
        )
    )

    await session.execute(delete(Artifact).where(Artifact.job_id.in_(job_ids)))
    await session.commit()

    for job in finished:
        if not job.workdir:
            continue
        # 디렉토리가 이미 사라졌어도 넘어간다. 여기서 터지면 로그아웃이 실패한다.
        shutil.rmtree(Path(job.workdir), ignore_errors=True)

    return freed


async def enforce_storage_quota(
    session: AsyncSession, owner_id: int, quota_bytes: int
) -> int:
    """이 사용자의 산출물 총량을 상한 아래로 되돌린다.

    **오래된 잡부터 버린다.** 최근 결과가 지금 화면에서 보고 있는 것이고,
    옛 결과는 소스만 있으면 다시 실행해 얻을 수 있다.

    **가장 최근 잡 하나는 남긴다.** 그것 하나가 상한보다 크더라도 그렇다 —
    방금 돌린 결과가 사라지면 사용자는 왜 결과가 없는지 알 수 없고, 다시
    돌려도 같은 일이 반복된다. 상한은 쌓이는 것을 막자는 것이지 마지막 결과를
    뺏자는 것이 아니다.

    도는 잡은 건드리지 않는다. 작업 디렉토리를 지우면 워커가 결과를 쓸 곳을
    잃는다.

    Returns:
        비운 바이트 수.
    """
    rows = (
        await session.execute(
            select(Job, func.coalesce(func.sum(Artifact.size_bytes), 0))
            .join(Artifact, Artifact.job_id == Job.id)
            .where(Job.owner_id == owner_id)
            .group_by(Job.id)
            .order_by(Job.created_at.desc(), Job.id.desc())
        )
    ).all()

    total = sum(size for _, size in rows)
    if total <= quota_bytes:
        return 0

    # 최신순으로 훑으며 상한을 넘기는 지점부터 버린다. 첫 번째(가장 최신)는
    # 위 이유로 건너뛴다.
    doomed: list[Job] = []
    kept = 0
    for index, (job, size) in enumerate(rows):
        if index == 0 or kept + size <= quota_bytes:
            kept += size
            continue
        if not job.status.is_terminal:
            # 도는 잡은 셈에는 넣되 지우지는 않는다.
            kept += size
            continue
        doomed.append(job)

    if not doomed:
        return 0

    job_ids = [job.id for job in doomed]
    freed = sum(
        artifact.size_bytes
        for artifact in await session.scalars(
            select(Artifact).where(Artifact.job_id.in_(job_ids))
        )
    )
    await session.execute(delete(Artifact).where(Artifact.job_id.in_(job_ids)))
    await session.commit()

    for job in doomed:
        if job.workdir:
            shutil.rmtree(Path(job.workdir), ignore_errors=True)

    logger.info(
        "상한 초과로 잡 %d 건의 산출물을 비웠습니다: user=%s, %d바이트",
        len(doomed),
        owner_id,
        freed,
    )
    return freed
