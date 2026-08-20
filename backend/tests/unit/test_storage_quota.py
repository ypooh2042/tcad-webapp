"""사용자별 산출물 총량 상한과 고아 작업디렉토리 청소.

`.str` 은 캐시라 지워도 되지만, **접속해 있는 동안에는 아무도 치우지 않는다.**
유휴 청소는 세션이 끝난 사용자만 보기 때문이다. 그래서 한 사람이 계속 실행하면
디스크가 무한히 찬다 — 잡 하나가 최대 256MB 다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Artifact, Base, Job, JobStatus, User
from app.jobs.cache import enforce_storage_quota
from app.jobs.sweeper import sweep_orphan_workdirs, sweep_over_quota

pytestmark = pytest.mark.integration


@pytest.fixture
async def sessionmaker_(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def make_user(maker, email="a@example.com") -> int:
    async with maker() as session:
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.commit()
        return user.id


async def make_job(
    maker, owner_id: int, root: Path, megabytes: int, minutes_ago: int
) -> int:
    """산출물 하나를 가진 끝난 잡. 디렉토리도 실제로 만든다."""
    workdir = root / f"job-{owner_id}-{minutes_ago}"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "out.str").write_bytes(b"x" * (megabytes * 1_048_576))

    async with maker() as session:
        job = Job(
            owner_id=owner_id,
            workdir=str(workdir),
            status=JobStatus.SUCCEEDED,
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )
        session.add(job)
        await session.flush()
        session.add(
            Artifact(
                job_id=job.id,
                filename="out.str",
                path=str(workdir / "out.str"),
                size_bytes=megabytes * 1_048_576,
                sequence=1,
            )
        )
        await session.commit()
        return job.id


async def artifact_count(maker) -> int:
    async with maker() as session:
        return len(list(await session.scalars(select(Artifact))))


MB = 1_048_576


class TestQuota:
    async def test_under_the_limit_nothing_happens(
        self, sessionmaker_, tmp_path
    ) -> None:
        owner = await make_user(sessionmaker_)
        await make_job(sessionmaker_, owner, tmp_path, megabytes=3, minutes_ago=10)

        async with sessionmaker_() as session:
            freed = await enforce_storage_quota(session, owner, 10 * MB)

        assert freed == 0
        assert await artifact_count(sessionmaker_) == 1

    async def test_drops_the_oldest_first(self, sessionmaker_, tmp_path) -> None:
        """최근 결과가 지금 보고 있는 것이다. 오래된 쪽부터 버려야 한다."""
        owner = await make_user(sessionmaker_)
        old = await make_job(sessionmaker_, owner, tmp_path, 4, minutes_ago=60)
        recent = await make_job(sessionmaker_, owner, tmp_path, 4, minutes_ago=1)

        async with sessionmaker_() as session:
            await enforce_storage_quota(session, owner, 5 * MB)

        async with sessionmaker_() as session:
            left = {a.job_id for a in await session.scalars(select(Artifact))}
        assert left == {recent}
        assert old not in left

    async def test_removes_the_files_too(self, sessionmaker_, tmp_path) -> None:
        """DB 행만 지우면 디스크는 그대로 차 있다."""
        owner = await make_user(sessionmaker_)
        await make_job(sessionmaker_, owner, tmp_path, 8, minutes_ago=60)
        await make_job(sessionmaker_, owner, tmp_path, 8, minutes_ago=1)

        async with sessionmaker_() as session:
            await enforce_storage_quota(session, owner, 10 * MB)

        # 최신 것만 남는다. 버린 쪽은 파일도 함께 사라져야 한다.
        assert len(list(tmp_path.glob("job-*/out.str"))) == 1

    async def test_keeps_at_least_the_newest(self, sessionmaker_, tmp_path) -> None:
        """가장 최근 결과 하나가 상한보다 커도 그것까지 버리지는 않는다.

        방금 돌린 것이 사라지면 사용자는 왜 결과가 없는지 알 수 없다. 상한은
        쌓이는 것을 막자는 것이지 마지막 결과를 뺏자는 것이 아니다.
        """
        owner = await make_user(sessionmaker_)
        only = await make_job(sessionmaker_, owner, tmp_path, 20, minutes_ago=1)

        async with sessionmaker_() as session:
            await enforce_storage_quota(session, owner, 1 * MB)

        async with sessionmaker_() as session:
            left = {a.job_id for a in await session.scalars(select(Artifact))}
        assert left == {only}

    async def test_other_users_are_untouched(self, sessionmaker_, tmp_path) -> None:
        mine = await make_user(sessionmaker_, "a@example.com")
        theirs = await make_user(sessionmaker_, "b@example.com")
        await make_job(sessionmaker_, mine, tmp_path, 8, minutes_ago=60)
        await make_job(sessionmaker_, mine, tmp_path, 8, minutes_ago=1)
        await make_job(sessionmaker_, theirs, tmp_path, 8, minutes_ago=60)

        async with sessionmaker_() as session:
            await enforce_storage_quota(session, mine, 1 * MB)

        async with sessionmaker_() as session:
            owners = {
                job.owner_id
                for job in await session.scalars(
                    select(Job).join(Artifact, Artifact.job_id == Job.id)
                )
            }
        assert theirs in owners

    async def test_running_jobs_are_never_touched(
        self, sessionmaker_, tmp_path
    ) -> None:
        """도는 잡의 디렉토리를 지우면 워커가 결과를 쓸 곳을 잃는다."""
        owner = await make_user(sessionmaker_)
        job_id = await make_job(sessionmaker_, owner, tmp_path, 8, minutes_ago=60)
        async with sessionmaker_() as session:
            job = await session.get(Job, job_id)
            job.status = JobStatus.RUNNING
            await session.commit()

        async with sessionmaker_() as session:
            freed = await enforce_storage_quota(session, owner, 1 * MB)

        assert freed == 0
        assert await artifact_count(sessionmaker_) == 1


class TestSweepOverQuota:
    async def test_applies_to_users_who_are_still_logged_in(
        self, sessionmaker_, tmp_path
    ) -> None:
        """유휴 청소와 달리 **접속 여부를 보지 않는다.**

        접속해 있는 동안 아무도 치우지 않는 것이 바로 디스크가 차는 경로다.
        """
        owner = await make_user(sessionmaker_)
        await make_job(sessionmaker_, owner, tmp_path, 8, minutes_ago=60)
        await make_job(sessionmaker_, owner, tmp_path, 8, minutes_ago=1)

        freed = await sweep_over_quota(sessionmaker_, quota_bytes=10 * MB)

        assert freed > 0
        assert await artifact_count(sessionmaker_) == 1


class TestOrphanDirectories:
    async def test_removes_directories_with_no_job_row(
        self, sessionmaker_, tmp_path
    ) -> None:
        """사용자를 지우면 잡 행은 CASCADE 로 사라지지만 디렉토리는 남는다."""
        orphan = tmp_path / "job-orphan"
        orphan.mkdir()
        (orphan / "out.str").write_bytes(b"x" * MB)
        _age(orphan, hours=5)

        freed = await sweep_orphan_workdirs(sessionmaker_, tmp_path)

        assert freed >= MB
        assert not orphan.exists()

    async def test_keeps_directories_a_job_still_points_at(
        self, sessionmaker_, tmp_path
    ) -> None:
        owner = await make_user(sessionmaker_)
        await make_job(sessionmaker_, owner, tmp_path, 1, minutes_ago=1)
        for path in tmp_path.iterdir():
            _age(path, hours=5)

        await sweep_orphan_workdirs(sessionmaker_, tmp_path)

        assert list(tmp_path.glob("job-*/out.str"))

    async def test_leaves_fresh_directories_alone(
        self, sessionmaker_, tmp_path
    ) -> None:
        """방금 만든 디렉토리는 아직 잡 행이 안 들어왔을 수 있다."""
        fresh = tmp_path / "job-fresh"
        fresh.mkdir()

        await sweep_orphan_workdirs(sessionmaker_, tmp_path)

        assert fresh.exists()

    async def test_missing_root_is_not_an_error(self, sessionmaker_, tmp_path) -> None:
        assert await sweep_orphan_workdirs(sessionmaker_, tmp_path / "없음") == 0


def _age(path: Path, hours: int) -> None:
    """디렉토리를 오래된 것처럼 만든다."""
    import os

    old = datetime.now(UTC).timestamp() - hours * 3600
    os.utime(path, (old, old))
