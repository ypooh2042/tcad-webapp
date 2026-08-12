"""산출물 캐시 정리.

`.str` 은 캐시다 — 소스만 남아 있으면 다시 실행해서 얻을 수 있고, 실행 한 번에
5MB 씩 쌓여 디스크를 가장 많이 먹는다. 그래서 세션이 끝나면 비운다.

**로그는 남긴다.** 무엇이 왜 실패했는지는 다시 실행해도 되살아나지 않는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, select
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
from app.jobs.cache import discard_artifacts


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _user(db, email: str) -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.commit()
    return user


async def _revision(db, user) -> SourceRevision:
    """잡은 아직 소스 리비전을 요구한다(NOT NULL)."""
    project = Project(owner_id=user.id, name=f"p-{user.id}")
    db.add(project)
    await db.flush()
    revision = SourceRevision(project_id=project.id, revision=1, source="x")
    db.add(revision)
    await db.commit()
    return revision


async def _job_with_artifacts(db, user, tmp_path, name: str) -> Job:
    workdir = tmp_path / name
    workdir.mkdir()
    (workdir / "a.str").write_text("x" * 100)

    job = Job(
        owner_id=user.id,
        source_revision_id=(await _revision(db, user)).id,
        status=JobStatus.SUCCEEDED,
        workdir=str(workdir),
        log="완료",
    )
    db.add(job)
    await db.flush()
    db.add(
        Artifact(
            job_id=job.id, filename="a.str", path=str(workdir / "a.str"),
            size_bytes=100, sequence=1,
        )
    )
    await db.commit()
    return job


class TestDiscard:
    async def test_removes_the_files(self, db, tmp_path):
        user = await _user(db, "a@example.com")
        job = await _job_with_artifacts(db, user, tmp_path, "job-1")

        await discard_artifacts(db, user.id)

        assert not (tmp_path / "job-1" / "a.str").exists()

    async def test_removes_the_rows(self, db, tmp_path):
        # 파일만 지우면 화면에 뜨는 목록이 전부 410 을 뱉는다.
        user = await _user(db, "a@example.com")
        await _job_with_artifacts(db, user, tmp_path, "job-1")

        await discard_artifacts(db, user.id)

        assert (await db.scalars(select(Artifact))).all() == []

    async def test_keeps_the_job_and_its_log(self, db, tmp_path):
        """로그는 다시 실행해도 되살아나지 않는다. 무엇이 왜 실패했는지가 남아야
        한다."""
        user = await _user(db, "a@example.com")
        job = await _job_with_artifacts(db, user, tmp_path, "job-1")

        await discard_artifacts(db, user.id)

        kept = await db.get(Job, job.id)
        assert kept is not None
        assert kept.log == "완료"

    async def test_reports_how_much_it_freed(self, db, tmp_path):
        user = await _user(db, "a@example.com")
        await _job_with_artifacts(db, user, tmp_path, "job-1")

        freed = await discard_artifacts(db, user.id)

        assert freed == 100

    async def test_leaves_other_users_alone(self, db, tmp_path):
        alice = await _user(db, "a@example.com")
        bob = await _user(db, "b@example.com")
        await _job_with_artifacts(db, alice, tmp_path, "job-a")
        await _job_with_artifacts(db, bob, tmp_path, "job-b")

        await discard_artifacts(db, alice.id)

        assert (tmp_path / "job-b" / "a.str").exists()
        assert len((await db.scalars(select(Artifact))).all()) == 1

    async def test_is_safe_to_run_twice(self, db, tmp_path):
        # 로그아웃 직후 스위퍼가 또 돌 수 있다.
        user = await _user(db, "a@example.com")
        await _job_with_artifacts(db, user, tmp_path, "job-1")

        await discard_artifacts(db, user.id)
        freed = await discard_artifacts(db, user.id)

        assert freed == 0

    async def test_survives_a_missing_workdir(self, db, tmp_path):
        """디렉토리가 이미 사라졌어도 행은 치워야 한다. 여기서 터지면 로그아웃이
        실패한다."""
        user = await _user(db, "a@example.com")
        await _job_with_artifacts(db, user, tmp_path, "job-1")
        import shutil

        shutil.rmtree(tmp_path / "job-1")

        await discard_artifacts(db, user.id)

        assert (await db.scalars(select(Artifact))).all() == []

    async def test_does_not_touch_running_jobs(self, db, tmp_path, ):
        """돌고 있는 잡의 작업 디렉토리를 지우면 워커가 결과를 쓸 곳을 잃는다."""
        user = await _user(db, "a@example.com")
        workdir = tmp_path / "job-live"
        workdir.mkdir()
        (workdir / "job.in").write_text("x")
        db.add(
            Job(
                owner_id=user.id,
                source_revision_id=(await _revision(db, user)).id,
                status=JobStatus.RUNNING, workdir=str(workdir), log="",
            )
        )
        await db.commit()

        await discard_artifacts(db, user.id)

        assert (workdir / "job.in").exists()
