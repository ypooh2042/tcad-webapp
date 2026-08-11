"""잡 큐.

DB 를 큐로 쓴다. 별도 브로커를 두지 않는 이유는 규모가 작고(동시 4개, 사용자
10명) 잡 상태를 어차피 DB 에 남겨야 하기 때문이다. 브로커를 추가하면 "브로커에는
있는데 DB 에는 없는" 어긋난 상태를 따로 다뤄야 한다.

동시 실행 상한은 로그인 정원(10명)과 별개다. 시뮬레이션은 CPU 를 오래 쓰고 이
홈서버는 다른 서비스와 코어를 나눠 쓴다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Job, JobStatus


class JobQueue:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        max_concurrent: int = 4,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.max_concurrent = max_concurrent

    async def enqueue(
        self, owner_id: int, source_revision_id: int, workdir: str
    ) -> Job:
        async with self.sessionmaker() as session:
            job = Job(
                owner_id=owner_id,
                source_revision_id=source_revision_id,
                workdir=workdir,
                status=JobStatus.QUEUED,
            )
            session.add(job)
            await session.commit()
            return job

    async def queued_count(self) -> int:
        return await self._count_with_status(JobStatus.QUEUED)

    async def running_count(self) -> int:
        return await self._count_with_status(JobStatus.RUNNING)

    async def claim_next(self) -> Job | None:
        """실행할 잡을 하나 선점한다. 없거나 정원이 찼으면 None.

        선점은 조건부 UPDATE 한 번으로 끝낸다. SELECT 로 고른 뒤 UPDATE 하면
        두 워커가 같은 잡을 집어가 시뮬레이션이 중복 실행될 수 있다. UPDATE 의
        WHERE 에 status 조건을 그대로 넣어 먼저 도착한 쪽만 성공하게 한다.
        """
        async with self.sessionmaker() as session:
            if await self._running_count(session) >= self.max_concurrent:
                return None

            candidate_id = await session.scalar(
                select(Job.id)
                .where(Job.status == JobStatus.QUEUED)
                .order_by(Job.created_at, Job.id)
                .limit(1)
            )
            if candidate_id is None:
                return None

            result = await session.execute(
                update(Job)
                .where(Job.id == candidate_id, Job.status == JobStatus.QUEUED)
                .values(
                    status=JobStatus.RUNNING,
                    started_at=datetime.now(timezone.utc),
                )
            )
            if result.rowcount == 0:
                # 다른 워커가 먼저 가져갔다. 경합은 정상이며 다음 호출에서
                # 다시 시도하면 된다.
                await session.rollback()
                return None

            await session.commit()
            return await session.get(Job, candidate_id)

    async def mark_finished(
        self,
        job_id: int,
        status: JobStatus,
        log: str,
        exit_code: int | None,
    ) -> None:
        """실행 결과를 기록한다.

        status 는 종료 코드가 아니라 로그 분석 결과에 근거해야 한다. 시뮬레이터는
        커맨드 오류가 있어도 exit 0 으로 끝난다(runner/results.py 참조).
        """
        if not status.is_terminal:
            raise ValueError(f"종료 상태가 아닙니다: {status}")

        async with self.sessionmaker() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(
                    status=status,
                    log=log,
                    exit_code=exit_code,
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

    async def requeue_stale(self, max_runtime: timedelta) -> int:
        """죽은 워커가 남긴 잡을 큐로 되돌린다.

        워커가 중간에 죽으면 잡이 RUNNING 상태로 남아 정원을 영구히 점유한다.
        그대로 두면 동시 실행 슬롯이 하나씩 사라지다가 큐 전체가 멈춘다.

        Returns:
            되돌린 잡 수.
        """
        cutoff = datetime.now(timezone.utc) - max_runtime
        async with self.sessionmaker() as session:
            result = await session.execute(
                update(Job)
                .where(Job.status == JobStatus.RUNNING, Job.started_at < cutoff)
                .values(status=JobStatus.QUEUED, started_at=None)
            )
            await session.commit()
            return result.rowcount

    async def _count_with_status(self, status: JobStatus) -> int:
        async with self.sessionmaker() as session:
            return await session.scalar(
                select(func.count()).select_from(Job).where(Job.status == status)
            )

    async def _running_count(self, session: AsyncSession) -> int:
        return await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.RUNNING)
        )
