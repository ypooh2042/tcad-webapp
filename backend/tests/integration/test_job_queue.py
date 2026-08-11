"""잡 큐 통합 테스트.

큐가 지켜야 할 것:
  - 동시 실행 수를 넘기지 않는다(6코어 홈서버에서 다른 서비스와 공존해야 한다)
  - 먼저 들어온 잡이 먼저 실행된다
  - 워커가 죽어도 잡이 RUNNING 에 영원히 갇히지 않는다
  - 같은 잡을 두 워커가 동시에 집어가지 않는다

DB 는 SQLite 로 돌린다. 주의: SQLite 는 쓰기를 직렬화하므로 아래 동시 선점
테스트는 **진짜 경합을 재현하지 못한다.** 조건부 UPDATE 로직이 논리적으로
맞는지 보는 스모크 테스트로만 의미가 있고, 실제 다중 워커 경합은 PostgreSQL
환경에서 별도로 확인해야 한다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base, Job, JobStatus, Project, SourceRevision, User
from app.jobs.queue import JobQueue

pytestmark = pytest.mark.integration


@pytest.fixture
async def sessionmaker_fixture():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def revision(sessionmaker_fixture):
    async with sessionmaker_fixture() as session:
        user = User(email="a@example.com", password_hash="x", role="user")
        session.add(user)
        await session.flush()
        project = Project(owner_id=user.id, name="p")
        session.add(project)
        await session.flush()
        rev = SourceRevision(project_id=project.id, revision=1, source="quit\n")
        session.add(rev)
        await session.commit()
        return rev


@pytest.fixture
def queue(sessionmaker_fixture) -> JobQueue:
    return JobQueue(sessionmaker_fixture, max_concurrent=4)


class TestEnqueue:
    async def test_new_job_starts_queued(self, queue, revision) -> None:
        job = await queue.enqueue(
            owner_id=1, source_revision_id=revision.id, workdir="/var/jobs/1"
        )
        assert job.status is JobStatus.QUEUED

    async def test_queued_jobs_are_counted(self, queue, revision) -> None:
        for i in range(3):
            await queue.enqueue(1, revision.id, f"/var/jobs/{i}")
        assert await queue.queued_count() == 3


class TestConcurrencyLimit:
    async def test_claims_up_to_the_limit(self, queue, revision) -> None:
        for i in range(10):
            await queue.enqueue(1, revision.id, f"/var/jobs/{i}")

        claimed = [await queue.claim_next() for _ in range(4)]
        assert all(job is not None for job in claimed)

    async def test_refuses_to_exceed_the_limit(self, queue, revision) -> None:
        """동시 실행이 상한을 넘으면 홈서버의 다른 서비스가 영향을 받는다."""
        for i in range(10):
            await queue.enqueue(1, revision.id, f"/var/jobs/{i}")

        for _ in range(4):
            await queue.claim_next()

        assert await queue.claim_next() is None

    async def test_finishing_a_job_frees_a_slot(self, queue, revision) -> None:
        for i in range(6):
            await queue.enqueue(1, revision.id, f"/var/jobs/{i}")
        running = [await queue.claim_next() for _ in range(4)]

        await queue.mark_finished(
            running[0].id, status=JobStatus.SUCCEEDED, log="ok", exit_code=0
        )

        assert await queue.claim_next() is not None


class TestOrdering:
    async def test_oldest_job_runs_first(self, queue, revision) -> None:
        first = await queue.enqueue(1, revision.id, "/var/jobs/first")
        second = await queue.enqueue(1, revision.id, "/var/jobs/second")

        assert (await queue.claim_next()).id == first.id
        assert (await queue.claim_next()).id == second.id


class TestClaiming:
    async def test_claimed_job_becomes_running(self, queue, revision) -> None:
        await queue.enqueue(1, revision.id, "/var/jobs/1")
        job = await queue.claim_next()

        assert job.status is JobStatus.RUNNING
        assert job.started_at is not None

    async def test_claimed_job_is_not_claimed_again(self, queue, revision) -> None:
        await queue.enqueue(1, revision.id, "/var/jobs/1")
        await queue.claim_next()

        assert await queue.claim_next() is None

    async def test_empty_queue_returns_none(self, queue) -> None:
        assert await queue.claim_next() is None

    async def test_concurrent_claims_never_duplicate(self, queue, revision) -> None:
        """두 워커가 동시에 같은 잡을 집어가면 시뮬레이션이 중복 실행된다.

        주의: SQLite 는 쓰기를 직렬화하므로 이 테스트는 진짜 경합을 재현하지
        않는다. 조건부 UPDATE 가 논리적으로 맞는지 보는 스모크 테스트다.
        """
        for i in range(4):
            await queue.enqueue(1, revision.id, f"/var/jobs/{i}")

        claimed = await asyncio.gather(*(queue.claim_next() for _ in range(4)))
        ids = [job.id for job in claimed if job is not None]

        assert len(ids) == len(set(ids))


class TestCompletion:
    async def test_records_outcome(self, queue, revision) -> None:
        await queue.enqueue(1, revision.id, "/var/jobs/1")
        job = await queue.claim_next()

        await queue.mark_finished(
            job.id, status=JobStatus.FAILED, log="errors detected", exit_code=0
        )

        async with queue.sessionmaker() as session:
            stored = await session.get(Job, job.id)
        assert stored.status is JobStatus.FAILED
        assert stored.log == "errors detected"
        assert stored.finished_at is not None

    async def test_failed_job_does_not_hold_a_slot(self, queue, revision) -> None:
        for i in range(5):
            await queue.enqueue(1, revision.id, f"/var/jobs/{i}")
        running = [await queue.claim_next() for _ in range(4)]
        await queue.mark_finished(
            running[0].id, status=JobStatus.FAILED, log="", exit_code=1
        )

        assert await queue.claim_next() is not None


class TestStaleRecovery:
    async def test_reclaims_jobs_abandoned_by_a_dead_worker(
        self, queue, revision
    ) -> None:
        """워커가 죽으면 잡이 RUNNING 인 채로 남아 정원을 영구히 점유한다."""
        await queue.enqueue(1, revision.id, "/var/jobs/1")
        job = await queue.claim_next()

        async with queue.sessionmaker() as session:
            stored = await session.get(Job, job.id)
            stored.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
            await session.commit()

        recovered = await queue.requeue_stale(max_runtime=timedelta(minutes=30))

        assert recovered == 1
        assert await queue.claim_next() is not None

    async def test_healthy_running_job_is_left_alone(self, queue, revision) -> None:
        await queue.enqueue(1, revision.id, "/var/jobs/1")
        await queue.claim_next()

        assert await queue.requeue_stale(max_runtime=timedelta(minutes=30)) == 0
