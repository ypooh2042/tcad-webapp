"""프로젝트·잡 API 통합 테스트.

가장 중요한 검증은 소유권 격리다. 잡 로그에는 사용자가 쓴 코드와 실행 결과가
그대로 들어 있으므로, 남의 것을 읽히면 안 되고 존재 여부조차 알려주면 안 된다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth, routes_jobs, routes_projects
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.db.models import Base
from app.jobs.queue import JobQueue
from tests.helpers import register

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
SOURCE = "init boron conc=1e15\nstructure out=a.str\n"


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


async def login_as(app, email: str) -> AsyncClient:
    """가입 + 로그인을 마친 클라이언트를 돌려준다."""
    client = AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    )
    await register(client, app.state.sessionmaker, email, PASSWORD)
    await client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )
    return client


@pytest.fixture
async def alice(app):
    client = await login_as(app, "alice@example.com")
    yield client
    await client.aclose()


@pytest.fixture
async def bob(app):
    client = await login_as(app, "bob@example.com")
    yield client
    await client.aclose()


async def make_project_with_source(client, name="proj") -> int:
    project_id = (
        await client.post("/api/projects", json={"name": name})
    ).json()["id"]
    await client.post(
        f"/api/projects/{project_id}/revisions", json={"source": SOURCE}
    )
    return project_id


class TestAuthRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/projects"),
            ("post", "/api/projects"),
            ("post", "/api/projects/1/revisions"),
            ("post", "/api/projects/1/jobs"),
            ("get", "/api/projects/1/jobs"),
            ("get", "/api/jobs/1"),
            ("get", "/api/jobs/1/artifacts/1"),
        ],
    )
    async def test_anonymous_is_rejected(self, app, method, path) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as anon:
            # httpx 의 get() 은 json 인자를 받지 않는다. 본문이 필요한 메서드만
            # 넘긴다.
            kwargs = {"json": {}} if method == "post" else {}
            response = await getattr(anon, method)(path, **kwargs)
        assert response.status_code == 401


class TestProjects:
    async def test_create_and_list(self, alice) -> None:
        await alice.post("/api/projects", json={"name": "cmos"})
        listed = (await alice.get("/api/projects")).json()

        assert [p["name"] for p in listed] == ["cmos"]

    async def test_duplicate_name_rejected(self, alice) -> None:
        await alice.post("/api/projects", json={"name": "dup"})
        response = await alice.post("/api/projects", json={"name": "dup"})

        assert response.status_code == 409

    async def test_other_user_may_reuse_name(self, alice, bob) -> None:
        await alice.post("/api/projects", json={"name": "shared-name"})
        response = await bob.post("/api/projects", json={"name": "shared-name"})

        assert response.status_code == 201

    async def test_listing_shows_only_own_projects(self, alice, bob) -> None:
        await alice.post("/api/projects", json={"name": "alice-only"})
        listed = (await bob.get("/api/projects")).json()

        assert listed == []


class TestRevisions:
    async def test_revision_numbers_increment(self, alice) -> None:
        project_id = (
            await alice.post("/api/projects", json={"name": "p"})
        ).json()["id"]

        first = await alice.post(
            f"/api/projects/{project_id}/revisions", json={"source": "a\n"}
        )
        second = await alice.post(
            f"/api/projects/{project_id}/revisions", json={"source": "b\n"}
        )

        assert first.json()["revision"] == 1
        assert second.json()["revision"] == 2

    async def test_cannot_add_revision_to_other_users_project(
        self, alice, bob
    ) -> None:
        project_id = await make_project_with_source(alice)
        response = await bob.post(
            f"/api/projects/{project_id}/revisions", json={"source": "evil\n"}
        )

        assert response.status_code == 404

    async def test_oversized_source_rejected(self, alice) -> None:
        project_id = (
            await alice.post("/api/projects", json={"name": "p"})
        ).json()["id"]
        response = await alice.post(
            f"/api/projects/{project_id}/revisions",
            json={"source": "x" * 200_001},
        )

        assert response.status_code == 422


class TestJobSubmission:
    async def test_submits_latest_revision(self, alice) -> None:
        project_id = await make_project_with_source(alice)
        response = await alice.post(f"/api/projects/{project_id}/jobs")

        assert response.status_code == 201
        assert response.json()["status"] == "queued"

    async def test_rejects_project_without_source(self, alice) -> None:
        project_id = (
            await alice.post("/api/projects", json={"name": "empty"})
        ).json()["id"]
        response = await alice.post(f"/api/projects/{project_id}/jobs")

        assert response.status_code == 400

    async def test_cannot_submit_to_other_users_project(self, alice, bob) -> None:
        project_id = await make_project_with_source(alice)
        response = await bob.post(f"/api/projects/{project_id}/jobs")

        assert response.status_code == 404

    async def test_workdir_is_random_not_derived_from_job_id(
        self, alice, app
    ) -> None:
        """순차 id 로 경로를 만들면 다른 잡의 디렉토리를 추측할 수 있다."""
        import re

        from app.db.models import Job

        project_id = await make_project_with_source(alice)
        job_ids = [
            (await alice.post(f"/api/projects/{project_id}/jobs")).json()["id"]
            for _ in range(2)
        ]

        async with app.state.sessionmaker() as session:
            workdirs = [(await session.get(Job, i)).workdir for i in job_ids]

        assert workdirs[0] != workdirs[1]
        for workdir in workdirs:
            assert re.fullmatch(r"job-[0-9a-f]{32}", workdir.rsplit("/", 1)[-1])


class TestJobVisibility:
    async def test_owner_sees_job_detail(self, alice) -> None:
        project_id = await make_project_with_source(alice)
        job_id = (
            await alice.post(f"/api/projects/{project_id}/jobs")
        ).json()["id"]

        response = await alice.get(f"/api/jobs/{job_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "queued"

    async def test_other_user_gets_404_not_403(self, alice, bob) -> None:
        """403 으로 답하면 그 잡이 존재한다는 사실이 드러난다."""
        project_id = await make_project_with_source(alice)
        job_id = (
            await alice.post(f"/api/projects/{project_id}/jobs")
        ).json()["id"]

        response = await bob.get(f"/api/jobs/{job_id}")

        assert response.status_code == 404

    async def test_missing_and_foreign_jobs_are_indistinguishable(
        self, alice, bob
    ) -> None:
        project_id = await make_project_with_source(alice)
        job_id = (
            await alice.post(f"/api/projects/{project_id}/jobs")
        ).json()["id"]

        foreign = await bob.get(f"/api/jobs/{job_id}")
        missing = await bob.get("/api/jobs/999999")

        assert foreign.status_code == missing.status_code
        assert foreign.json() == missing.json()

    async def test_cannot_read_other_users_artifacts(self, alice, bob) -> None:
        project_id = await make_project_with_source(alice)
        job_id = (
            await alice.post(f"/api/projects/{project_id}/jobs")
        ).json()["id"]

        response = await bob.get(f"/api/jobs/{job_id}/artifacts/1")

        assert response.status_code == 404

    async def test_project_job_list_is_scoped_to_owner(self, alice, bob) -> None:
        project_id = await make_project_with_source(alice)
        await alice.post(f"/api/projects/{project_id}/jobs")

        assert (await bob.get(f"/api/projects/{project_id}/jobs")).status_code == 404
        assert len((await alice.get(f"/api/projects/{project_id}/jobs")).json()) == 1


class TestLoadingSource:
    """프로젝트를 열면 저장해 둔 소스가 나와야 한다.

    이게 없으면 탭을 눌러도 편집기에는 이전 프로젝트의 내용이 그대로 남는다 —
    사용자는 다른 프로젝트를 보고 있다고 믿으면서 엉뚱한 소스를 고치게 된다.
    """

    async def test_returns_the_latest_revision(self, alice) -> None:
        project_id = await make_project_with_source(alice)
        await alice.post(
            f"/api/projects/{project_id}/revisions", json={"source": "second\n"}
        )

        body = (
            await alice.get(f"/api/projects/{project_id}/revisions/latest")
        ).json()

        assert body["source"] == "second\n"
        assert body["revision"] == 2

    async def test_project_without_source_is_404(self, alice) -> None:
        project_id = (
            await alice.post("/api/projects", json={"name": "empty"})
        ).json()["id"]

        response = await alice.get(f"/api/projects/{project_id}/revisions/latest")

        assert response.status_code == 404

    async def test_other_users_project_is_404(self, alice, bob) -> None:
        project_id = await make_project_with_source(alice)

        response = await bob.get(f"/api/projects/{project_id}/revisions/latest")

        assert response.status_code == 404

    async def test_anonymous_is_rejected(self, app) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as anon:
            response = await anon.get("/api/projects/1/revisions/latest")

        assert response.status_code == 401
