"""잡 조회가 실행 시간과 공정 진행을 함께 알려주는지.

둘 다 **도는 동안** 쓸모가 있어야 하는 값이다. 로그는 실행이 끝나야 들어오므로,
이것들이 없으면 사용자는 몇 분 동안 "실행 중" 세 글자만 본다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth, routes_jobs, routes_projects
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.db.models import Base, Job, JobStatus
from app.jobs.queue import JobQueue
from tests.helpers import register

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
SOURCE = (
    "init boron conc=1e15\n"
    "structure out=well.str\n"
    "diffuse time=30 temp=1000\n"
    "structure out=oxidation.str\n"
    "etch oxide all\n"
    "structure out=final.str\n"
)


@pytest.fixture
async def app(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    application = FastAPI()
    application.include_router(routes_auth.router, prefix="/api")
    application.include_router(routes_projects.router, prefix="/api")
    application.include_router(routes_jobs.router, prefix="/api")
    application.state.settings = Settings(
        session_cookie_secure=False, jobs_root=tmp_path
    )
    application.state.sessionmaker = maker
    application.state.session_store = InMemorySessionStore()
    application.state.session_policy = SessionPolicy()
    application.state.queue = JobQueue(maker, max_concurrent=4)

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        await register(
            async_client, app.state.sessionmaker, "alice@example.com", PASSWORD
        )
        await async_client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": PASSWORD},
        )
        yield async_client


async def owner_id(app) -> int:
    from app.db.models import User
    from sqlalchemy import select

    async with app.state.sessionmaker() as session:
        return (await session.execute(select(User.id))).scalars().first()


async def make_job(
    app,
    workdir: Path,
    status: JobStatus,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> int:
    async with app.state.sessionmaker() as session:
        job = Job(
            owner_id=await owner_id(app),
            source_path="cmos.in",
            source=SOURCE,
            status=status,
            workdir=str(workdir),
            started_at=started_at,
            finished_at=finished_at,
        )
        session.add(job)
        await session.commit()
        return job.id


def now() -> datetime:
    """호출 시점의 시각.

    모듈 상수로 두면 안 된다. 임포트 시각에 고정되므로, 전체 스위트를 돌릴 때
    이 테스트가 실행되기까지 흐른 시간이 그대로 경과 시간에 더해진다(실제로
    그렇게 깨졌다).
    """
    return datetime.now(timezone.utc)


class TestElapsed:
    async def test_running_job_reports_time_so_far(self, app, client) -> None:
        job_id = await make_job(
            app,
            Path("/nonexistent"),
            JobStatus.RUNNING,
            started_at=now() - timedelta(seconds=70),
        )
        elapsed = (await client.get(f"/api/jobs/{job_id}")).json()["elapsed_seconds"]
        assert 69 <= elapsed <= 75

    async def test_finished_job_reports_total_run_time(self, app, client) -> None:
        started = now() - timedelta(minutes=10)
        job_id = await make_job(
            app,
            Path("/nonexistent"),
            JobStatus.SUCCEEDED,
            started_at=started,
            finished_at=started + timedelta(seconds=95),
        )
        body = (await client.get(f"/api/jobs/{job_id}")).json()
        assert body["elapsed_seconds"] == pytest.approx(95, abs=0.5)

    async def test_finished_time_does_not_keep_growing(self, app, client) -> None:
        """끝난 잡을 두 번 조회하면 같은 값이어야 한다."""
        started = now() - timedelta(minutes=10)
        job_id = await make_job(
            app,
            Path("/nonexistent"),
            JobStatus.FAILED,
            started_at=started,
            finished_at=started + timedelta(seconds=12),
        )
        first = (await client.get(f"/api/jobs/{job_id}")).json()["elapsed_seconds"]
        second = (await client.get(f"/api/jobs/{job_id}")).json()["elapsed_seconds"]
        assert first == second

    async def test_queued_job_has_no_run_time(self, app, client) -> None:
        """큐에서 기다린 시간은 실행 시간이 아니다."""
        job_id = await make_job(app, Path("/nonexistent"), JobStatus.QUEUED)
        body = (await client.get(f"/api/jobs/{job_id}")).json()
        assert body["elapsed_seconds"] is None


class TestProgress:
    async def test_running_job_reports_the_last_saved_step(
        self, app, client, tmp_path
    ) -> None:
        workdir = tmp_path / "job-abc"
        workdir.mkdir()
        (workdir / "well.str").write_text("x")
        (workdir / "oxidation.str").write_text("x")

        job_id = await make_job(
            app, workdir, JobStatus.RUNNING, started_at=now()
        )
        progress = (await client.get(f"/api/jobs/{job_id}")).json()["progress"]

        assert progress == {"done": 2, "total": 3, "latest": "oxidation.str"}

    async def test_finished_job_reports_no_progress(
        self, app, client, tmp_path
    ) -> None:
        """끝난 뒤에도 남으면 화면에 지워지지 않는 문구가 붙는다."""
        workdir = tmp_path / "job-done"
        workdir.mkdir()
        (workdir / "well.str").write_text("x")

        job_id = await make_job(
            app,
            workdir,
            JobStatus.SUCCEEDED,
            started_at=now(),
            finished_at=now(),
        )
        assert (await client.get(f"/api/jobs/{job_id}")).json()["progress"] is None

    async def test_queued_job_reports_no_progress(self, app, client) -> None:
        job_id = await make_job(app, Path("/nonexistent"), JobStatus.QUEUED)
        assert (await client.get(f"/api/jobs/{job_id}")).json()["progress"] is None

    async def test_cleaned_workdir_does_not_break_the_lookup(
        self, app, client, tmp_path
    ) -> None:
        job_id = await make_job(
            app, tmp_path / "gone", JobStatus.RUNNING, started_at=now()
        )
        response = await client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["progress"] is None
