"""인증 API 통합 테스트.

메모리 세션 저장소와 SQLite 를 물려 앱 전체를 띄운다. 외부 서비스 없이 돌아야
CI 에서도 항상 실행된다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.auth.passwords import hash_password
from app.db.models import Base, User
from tests.helpers import fresh_invite_code

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
async def app_and_state():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(routes_auth.router, prefix="/api")
    app.state.settings = Settings(session_cookie_secure=False)
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.session_store = InMemorySessionStore()
    app.state.session_policy = SessionPolicy()

    yield app
    await engine.dispose()


@pytest.fixture
async def client(app_and_state):
    transport = ASGITransport(app=app_and_state)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        # 가입에 초대 코드가 필요하다. 테스트에서 그 요구를 끄는 설정은 두지
        # 않는다 — 끌 수 있으면 배포에서 실수로 꺼질 수 있고, 그 순간 가입이
        # 개방된다. 대신 테스트가 실제로 초대를 발급해서 쓴다.
        async_client.sessionmaker = app_and_state.state.sessionmaker
        yield async_client


async def seed_users(app, count: int) -> None:
    """계정을 DB 에 직접 만든다. 가입 경로(초대·빈도 제한)를 우회한다."""
    async with app.state.sessionmaker() as session:
        for i in range(count):
            session.add(
                User(
                    email=f"user{i}@example.com",
                    password_hash=hash_password(PASSWORD),
                    role="user",
                )
            )
        await session.commit()


async def signup(client, email: str, password: str = PASSWORD):
    """초대를 발급해 가입 요청을 보낸다. 상태 코드는 호출부가 판정한다."""
    return await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "invite_code": await fresh_invite_code(client.sessionmaker),
        },
    )


async def register(client, email: str) -> None:
    response = await signup(client, email)
    assert response.status_code == 201, response.text


class TestRegistration:
    async def test_creates_account(self, client) -> None:
        response = await signup(client, "a@example.com", password=PASSWORD)
        assert response.status_code == 201
        assert response.json()["email"] == "a@example.com"

    async def test_rejects_duplicate_email(self, client) -> None:
        await register(client, "dup@example.com")
        response = await signup(client, "dup@example.com", password=PASSWORD)
        assert response.status_code == 409

    async def test_email_is_case_insensitive(self, client) -> None:
        await register(client, "Mixed@Example.com")
        response = await signup(client, "mixed@example.com", password=PASSWORD)
        assert response.status_code == 409

    async def test_rejects_short_password(self, client) -> None:
        response = await signup(client, "b@example.com", password="short")
        assert response.status_code == 422

    async def test_never_returns_password_hash(self, client) -> None:
        response = await signup(client, "c@example.com", password=PASSWORD)
        assert "password" not in response.text
        assert "argon2" not in response.text


class TestLogin:
    async def test_sets_session_cookie(self, client) -> None:
        await register(client, "a@example.com")
        response = await client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
        )
        assert response.status_code == 200
        assert "tcad_session" in response.cookies

    async def test_cookie_is_httponly(self, client) -> None:
        """JS 가 읽을 수 있으면 XSS 한 번으로 세션이 새어나간다."""
        await register(client, "a@example.com")
        response = await client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
        )
        assert "httponly" in response.headers["set-cookie"].lower()

    async def test_cookie_is_samesite_lax(self, client) -> None:
        await register(client, "a@example.com")
        response = await client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
        )
        assert "samesite=lax" in response.headers["set-cookie"].lower()

    async def test_wrong_password_rejected(self, client) -> None:
        await register(client, "a@example.com")
        response = await client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": "wrong-password"}
        )
        assert response.status_code == 401

    async def test_unknown_and_wrong_password_are_indistinguishable(
        self, client
    ) -> None:
        """응답이 다르면 가입된 이메일 목록을 만들 수 있다."""
        await register(client, "a@example.com")

        wrong = await client.post(
            "/api/auth/login",
            json={"email": "a@example.com", "password": "wrong-password"},
        )
        missing = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "wrong-password"},
        )

        assert wrong.status_code == missing.status_code == 401
        assert wrong.json() == missing.json()


class TestProtectedRoutes:
    async def test_me_requires_login(self, client) -> None:
        assert (await client.get("/api/auth/me")).status_code == 401

    async def test_me_returns_current_user(self, client) -> None:
        await register(client, "a@example.com")
        await client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
        )
        response = await client.get("/api/auth/me")

        assert response.status_code == 200
        assert response.json()["email"] == "a@example.com"

    async def test_logout_invalidates_session(self, client) -> None:
        await register(client, "a@example.com")
        await client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
        )
        assert (await client.post("/api/auth/logout")).status_code == 204
        assert (await client.get("/api/auth/me")).status_code == 401

    async def test_forged_cookie_rejected(self, client) -> None:
        client.cookies.set("tcad_session", "made-up-session-id")
        assert (await client.get("/api/auth/me")).status_code == 401


class TestConcurrentLimitOverHttp:
    async def test_eleventh_login_is_refused(self, app_and_state) -> None:
        """정원이 차면 503 으로 거절한다."""
        transport = ASGITransport(app=app_and_state)

        # 계정은 DB 에 직접 심는다. HTTP 가입을 11번 하면 가입 빈도 제한에
        # 먼저 걸리는데, 이 테스트가 보려는 것은 **세션 정원**이다.
        await seed_users(app_and_state, 11)

        for i in range(10):
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as user_client:
                response = await user_client.post(
                    "/api/auth/login",
                    json={"email": f"user{i}@example.com", "password": PASSWORD},
                )
                assert response.status_code == 200

        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as extra_client:
            response = await extra_client.post(
                "/api/auth/login",
                json={"email": "user10@example.com", "password": PASSWORD},
            )

        assert response.status_code == 503
        assert "정원" in response.json()["detail"]
