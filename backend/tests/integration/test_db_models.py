"""DB 스키마 통합 테스트.

스키마가 지켜야 할 것들을 검증한다. 특히 소스 리비전과 잡의 관계 — 잡은 실행
당시의 소스를 가리켜야 하고, 나중에 사용자가 코드를 고쳐도 과거 결과의 입력이
바뀌면 안 된다.

SQLite(aiosqlite)로 돌린다. 운영은 PostgreSQL 이지만 여기서 보는 제약(FK,
UNIQUE, CASCADE)은 양쪽 동일하게 동작한다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import (
    Artifact,
    Base,
    Job,
    JobStatus,
    Project,
    SourceRevision,
    User,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # SQLite 는 기본적으로 외래키를 강제하지 않는다. 켜주지 않으면 CASCADE 와
    # FK 제약 테스트가 통과한 것처럼 보이지만 실제로는 아무것도 검증하지 않는다.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


async def make_user(session, email="a@example.com", role="user") -> User:
    user = User(email=email, password_hash="$argon2id$dummy", role=role)
    session.add(user)
    await session.commit()
    return user


async def make_revision(session, user, source="init boron conc=1e15\n") -> SourceRevision:
    project = Project(owner_id=user.id, name="proj")
    session.add(project)
    await session.flush()
    revision = SourceRevision(project_id=project.id, revision=1, source=source)
    session.add(revision)
    await session.commit()
    return revision


class TestUsers:
    async def test_email_is_unique(self, session) -> None:
        await make_user(session, "dup@example.com")
        session.add(
            User(email="dup@example.com", password_hash="x", role="user")
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_role_is_constrained(self, session) -> None:
        """오타 난 권한값이 들어가면 관리자 면제 판정이 조용히 틀어진다."""
        session.add(User(email="b@example.com", password_hash="x", role="administrator"))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_admin_role_allowed(self, session) -> None:
        user = await make_user(session, "root@example.com", role="admin")
        assert user.role == "admin"


class TestProjects:
    async def test_name_unique_per_owner(self, session) -> None:
        user = await make_user(session)
        session.add(Project(owner_id=user.id, name="same"))
        await session.commit()
        session.add(Project(owner_id=user.id, name="same"))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_different_owners_may_reuse_a_name(self, session) -> None:
        first = await make_user(session, "one@example.com")
        second = await make_user(session, "two@example.com")
        session.add_all(
            [
                Project(owner_id=first.id, name="cmos"),
                Project(owner_id=second.id, name="cmos"),
            ]
        )
        await session.commit()


class TestSourceRevisions:
    async def test_revision_number_unique_per_project(self, session) -> None:
        user = await make_user(session)
        revision = await make_revision(session, user)
        session.add(
            SourceRevision(project_id=revision.project_id, revision=1, source="x")
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_job_keeps_its_source_when_project_gets_new_revision(
        self, session
    ) -> None:
        """핵심 요구: 결과는 실행 당시의 소스와 짝지어져야 한다.

        사용자가 코드를 고쳐 새 리비전을 만들어도, 이미 끝난 잡이 가리키는
        소스는 그대로여야 재현이 가능하다.
        """
        user = await make_user(session)
        first = await make_revision(session, user, source="original source\n")

        job = Job(
            owner_id=user.id, source_revision_id=first.id, workdir="/var/jobs/1"
        )
        session.add(job)
        await session.commit()

        session.add(
            SourceRevision(
                project_id=first.project_id, revision=2, source="edited source\n"
            )
        )
        await session.commit()

        loaded = await session.get(Job, job.id)
        revision = await session.get(SourceRevision, loaded.source_revision_id)
        assert revision.source == "original source\n"


class TestJobs:
    async def test_defaults_to_queued(self, session) -> None:
        user = await make_user(session)
        revision = await make_revision(session, user)
        job = Job(owner_id=user.id, source_revision_id=revision.id, workdir="/w")
        session.add(job)
        await session.commit()

        assert job.status is JobStatus.QUEUED

    async def test_terminal_status_classification(self) -> None:
        assert not JobStatus.QUEUED.is_terminal
        assert not JobStatus.RUNNING.is_terminal
        assert JobStatus.SUCCEEDED.is_terminal
        assert JobStatus.FAILED.is_terminal
        assert JobStatus.TIMED_OUT.is_terminal
        assert JobStatus.CANCELLED.is_terminal

    async def test_rejects_unknown_source_revision(self, session) -> None:
        user = await make_user(session)
        session.add(Job(owner_id=user.id, source_revision_id=9999, workdir="/w"))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_queue_ordering_is_oldest_first(self, session) -> None:
        user = await make_user(session)
        revision = await make_revision(session, user)
        for _ in range(3):
            session.add(
                Job(
                    owner_id=user.id,
                    source_revision_id=revision.id,
                    workdir="/w",
                )
            )
            await session.commit()

        queued = (
            await session.execute(
                select(Job)
                .where(Job.status == JobStatus.QUEUED)
                .order_by(Job.created_at, Job.id)
            )
        ).scalars().all()
        assert [job.id for job in queued] == sorted(job.id for job in queued)


class TestArtifacts:
    async def test_sequence_unique_per_job(self, session) -> None:
        user = await make_user(session)
        revision = await make_revision(session, user)
        job = Job(owner_id=user.id, source_revision_id=revision.id, workdir="/w")
        session.add(job)
        await session.flush()

        session.add(
            Artifact(
                job_id=job.id,
                filename="a.str",
                path="/w/a.str",
                size_bytes=1,
                sequence=1,
            )
        )
        await session.commit()
        session.add(
            Artifact(
                job_id=job.id,
                filename="b.str",
                path="/w/b.str",
                size_bytes=1,
                sequence=1,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_deleting_job_removes_its_artifacts(self, session) -> None:
        user = await make_user(session)
        revision = await make_revision(session, user)
        job = Job(owner_id=user.id, source_revision_id=revision.id, workdir="/w")
        session.add(job)
        await session.flush()
        session.add(
            Artifact(
                job_id=job.id,
                filename="a.str",
                path="/w/a.str",
                size_bytes=1,
                sequence=1,
            )
        )
        await session.commit()

        await session.delete(job)
        await session.commit()

        remaining = (await session.execute(select(Artifact))).scalars().all()
        assert remaining == []
