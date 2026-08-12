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

from sqlalchemy import delete, select
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
