"""애플리케이션 기동 경로.

다른 API 테스트는 라우터만 꺼내 자기 앱을 조립하고 메모리 저장소를 끼운다.
그래서 create_app 과 lifespan — 실제 배포에서 유일하게 쓰이는 경로 — 은 어떤
테스트도 지나가지 않는다. 엔진 URL 을 잘못 읽거나 Redis 를 안 물려도 전부
초록불로 보인다.

여기서는 진짜 PostgreSQL 과 Redis 에 붙여, 마이그레이션으로 만든 스키마 위에서
가입부터 잡 제출까지 한 번 흘려본다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
SOURCE = "init boron conc=1e15\nstructure out=a.str\n"


@pytest.fixture
def settings(migrated_database_url, redis_url, tmp_path) -> Settings:
    return Settings(
        database_url=migrated_database_url,
        redis_url=redis_url,
        jobs_root=tmp_path / "jobs",
        # httpx 는 http:// 로 오는 Secure 쿠키를 되돌려 보내지 않는다.
        session_cookie_secure=False,
    )


@pytest.fixture
async def client(settings):
    """lifespan 을 실제로 태운 클라이언트.

    ASGITransport 는 lifespan 을 돌리지 않는다. 직접 열어 주지 않으면 app.state
    가 비어 모든 요청이 500 이 되고, 정작 검증하려던 배선은 지나가지 않는다.
    """
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            client.app = app
            yield client


class TestLifespan:
    async def test_wires_dependencies_into_state(self, settings) -> None:
        app = create_app(settings)

        assert not hasattr(app.state, "sessionmaker")

        async with app.router.lifespan_context(app):
            assert app.state.sessionmaker is not None
            assert app.state.session_store is not None
            assert app.state.queue is not None

    async def test_queue_capacity_follows_settings(self, settings) -> None:
        app = create_app(settings)

        async with app.router.lifespan_context(app):
            assert app.state.queue.max_concurrent == settings.max_concurrent_jobs

    async def test_health_needs_no_authentication(self, client) -> None:
        response = await client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestRealStackFlow:
    """가입 → 로그인 → 프로젝트 → 리비전 → 잡 제출을 실제 스택 위에서 한 번."""

    async def test_full_submission_flow(self, client) -> None:
        registered = await client.post(
            "/api/auth/register",
            json={"email": "startup@example.com", "password": PASSWORD},
        )
        assert registered.status_code == 201, registered.text

        logged_in = await client.post(
            "/api/auth/login",
            json={"email": "startup@example.com", "password": PASSWORD},
        )
        assert logged_in.status_code == 200, logged_in.text

        project = await client.post("/api/projects", json={"name": "startup"})
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        revision = await client.post(
            f"/api/projects/{project_id}/revisions", json={"source": SOURCE}
        )
        assert revision.status_code == 201, revision.text

        job = await client.post(f"/api/projects/{project_id}/jobs")
        assert job.status_code == 201, job.text
        assert job.json()["status"] == "queued"

    async def test_session_survives_in_redis_not_memory(self, client) -> None:
        """세션이 프로세스 메모리에 있으면 워커·다중 프로세스에서 공유되지 않는다."""
        await client.post(
            "/api/auth/register",
            json={"email": "redis@example.com", "password": PASSWORD},
        )
        await client.post(
            "/api/auth/login",
            json={"email": "redis@example.com", "password": PASSWORD},
        )

        store = client.app.state.session_store
        policy = client.app.state.session_policy
        active = await store.active_sessions(
            now=datetime.now(timezone.utc), idle_timeout=policy.idle_timeout
        )

        assert len(active) == 1

    async def test_unauthenticated_request_is_rejected(self, client) -> None:
        response = await client.get("/api/projects")

        assert response.status_code == 401
