"""세션이 끝난 사용자의 산출물 정리.

로그아웃은 사용자가 눌러야 일어난다. **브라우저만 닫으면 아무 일도 없다** —
그 경우 `.str` 이 그대로 남아 디스크를 먹는다. 세션이 만료된 사용자를 주기적
으로 훑어 비운다.

정리 대상은 **활성 세션이 없는 사용자**다. 돌고 있는 잡은 건드리지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.models import Role, Session
from app.auth.store import InMemorySessionStore
from app.db.models import Artifact, Base, Job, JobStatus, User
from app.jobs.sweeper import sweep_idle_artifacts

IDLE = timedelta(minutes=30)


@pytest.fixture
async def sessionmaker_():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _user_with_artifact(maker, tmp_path, email: str) -> int:
    workdir = tmp_path / email
    workdir.mkdir()
    (workdir / "a.str").write_text("x" * 50)

    async with maker() as db:
        user = User(email=email, password_hash="x")
        db.add(user)
        await db.flush()
        job = Job(
            owner_id=user.id,
            source_revision_id=None,
            source_path="a.in",
            source="x",
            status=JobStatus.SUCCEEDED,
            workdir=str(workdir),
            log="완료",
        )
        db.add(job)
        await db.flush()
        db.add(
            Artifact(
                job_id=job.id, filename="a.str", path=str(workdir / "a.str"),
                size_bytes=50, sequence=1,
            )
        )
        await db.commit()
        return user.id


def _session(user_id: int, now: datetime) -> Session:
    return Session(
        id=f"s-{user_id}",
        user_id=str(user_id),
        role=Role.USER,
        created_at=now,
        last_seen_at=now,
    )


class TestSweep:
    async def test_clears_users_without_a_session(self, sessionmaker_, tmp_path):
        user_id = await _user_with_artifact(sessionmaker_, tmp_path, "gone")
        store = InMemorySessionStore()

        freed = await sweep_idle_artifacts(sessionmaker_, store, IDLE)

        assert freed == 50
        assert not (tmp_path / "gone" / "a.str").exists()
        async with sessionmaker_() as db:
            assert (await db.scalars(select(Artifact))).all() == []

    async def test_leaves_users_with_an_active_session(
        self, sessionmaker_, tmp_path
    ):
        """접속 중인 사용자의 결과를 지우면 보고 있던 그래프가 사라진다."""
        user_id = await _user_with_artifact(sessionmaker_, tmp_path, "here")
        store = InMemorySessionStore()
        now = datetime.now(timezone.utc)
        await store.save(_session(user_id, now), IDLE)

        freed = await sweep_idle_artifacts(sessionmaker_, store, IDLE)

        assert freed == 0
        assert (tmp_path / "here" / "a.str").exists()

    async def test_clears_only_the_idle_user(self, sessionmaker_, tmp_path):
        active = await _user_with_artifact(sessionmaker_, tmp_path, "active")
        await _user_with_artifact(sessionmaker_, tmp_path, "idle")
        store = InMemorySessionStore()
        await store.save(_session(active, datetime.now(timezone.utc)), IDLE)

        await sweep_idle_artifacts(sessionmaker_, store, IDLE)

        assert (tmp_path / "active" / "a.str").exists()
        assert not (tmp_path / "idle" / "a.str").exists()

    async def test_does_not_touch_running_jobs(self, sessionmaker_, tmp_path):
        # 워커가 결과를 쓸 곳을 잃는다.
        workdir = tmp_path / "live"
        workdir.mkdir()
        (workdir / "job.in").write_text("x")
        async with sessionmaker_() as db:
            user = User(email="live@example.com", password_hash="x")
            db.add(user)
            await db.flush()
            db.add(
                Job(
                    owner_id=user.id, source_revision_id=None, source="x",
                    status=JobStatus.RUNNING, workdir=str(workdir), log="",
                )
            )
            await db.commit()

        await sweep_idle_artifacts(sessionmaker_, InMemorySessionStore(), IDLE)

        assert (workdir / "job.in").exists()

    async def test_is_safe_when_there_is_nothing_to_do(self, sessionmaker_):
        assert await sweep_idle_artifacts(
            sessionmaker_, InMemorySessionStore(), IDLE
        ) == 0

    async def test_running_twice_frees_nothing_more(self, sessionmaker_, tmp_path):
        await _user_with_artifact(sessionmaker_, tmp_path, "twice")
        store = InMemorySessionStore()

        await sweep_idle_artifacts(sessionmaker_, store, IDLE)
        again = await sweep_idle_artifacts(sessionmaker_, store, IDLE)

        assert again == 0


class TestSweepLoop:
    """워커에 붙는 주기 실행."""

    async def test_stops_when_asked(self):
        import asyncio
        from app.jobs.sweeper import run_sweeper

        stop = asyncio.Event()
        calls = 0

        async def sweep() -> int:
            nonlocal calls
            calls += 1
            stop.set()
            return 0

        await asyncio.wait_for(run_sweeper(sweep, stop, interval=0.01), timeout=2)

        assert calls >= 1

    async def test_keeps_going_after_a_failure(self):
        """한 번 실패했다고 청소가 영영 멈추면 디스크가 계속 찬다."""
        import asyncio
        from app.jobs.sweeper import run_sweeper

        stop = asyncio.Event()
        calls = 0

        async def sweep() -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("일시적 실패")
            stop.set()
            return 0

        await asyncio.wait_for(run_sweeper(sweep, stop, interval=0.01), timeout=2)

        assert calls >= 2


class TestAdminSessions:
    """관리자 세션은 만료되지 않는다(정원·유휴 면제).

    그 면제를 산출물 청소에까지 적용하면 **관리자는 로그아웃하지 않는 한 영영
    정리되지 않는다** — 실제로 운영에서 97MB 가 그렇게 쌓였다. 청소는 "지금
    화면을 보고 있는가"만 따지면 되므로 마지막 활동 시각으로 판단한다.
    """

    async def test_clears_an_idle_admin(self, sessionmaker_, tmp_path):
        user_id = await _user_with_artifact(sessionmaker_, tmp_path, "admin-idle")
        store = InMemorySessionStore()
        stale = datetime.now(timezone.utc) - timedelta(hours=2)
        await store.save(
            Session(
                id=f"s-{user_id}", user_id=str(user_id), role=Role.ADMIN,
                created_at=stale, last_seen_at=stale,
            ),
            None,
        )

        freed = await sweep_idle_artifacts(sessionmaker_, store, IDLE)

        assert freed == 50
        assert not (tmp_path / "admin-idle" / "a.str").exists()

    async def test_keeps_a_working_admin(self, sessionmaker_, tmp_path):
        # 방금까지 보고 있었다면 그래프를 지우면 안 된다.
        user_id = await _user_with_artifact(sessionmaker_, tmp_path, "admin-busy")
        store = InMemorySessionStore()
        now = datetime.now(timezone.utc)
        await store.save(
            Session(
                id=f"s-{user_id}", user_id=str(user_id), role=Role.ADMIN,
                created_at=now, last_seen_at=now,
            ),
            None,
        )

        freed = await sweep_idle_artifacts(sessionmaker_, store, IDLE)

        assert freed == 0
        assert (tmp_path / "admin-busy" / "a.str").exists()
