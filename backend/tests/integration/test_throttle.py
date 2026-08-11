"""빈도 제한이 실제 엔드포인트에 걸려 있는지.

한도 값 자체가 설계 판단이다. **로그인 IP 한도는 동시 접속 정원(10명)보다
넉넉해야 한다** — 연구실 사람들은 같은 NAT 뒤에 있어 서버가 보는 IP 가 하나다.
처음에 10회/분으로 잡았다가 정원을 채우기도 전에 429 가 나는 것을 테스트에서
발견했다. 무차별 대입 방어는 계정별 한도가 맡는다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth
from app.api import throttle
from app.auth.passwords import hash_password
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.db.models import Base, User
from tests.helpers import PASSWORD, fresh_invite_code

pytestmark = pytest.mark.integration


@pytest.fixture
async def app():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    application = FastAPI()
    application.include_router(routes_auth.router, prefix="/api")
    application.state.settings = Settings(session_cookie_secure=False)
    application.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    application.state.session_store = InMemorySessionStore()
    application.state.session_policy = SessionPolicy()

    async with application.state.sessionmaker() as session:
        session.add(
            User(email="a@example.com", password_hash=hash_password(PASSWORD))
        )
        await session.commit()

    yield application
    await engine.dispose()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


class TestLoginBruteForce:
    async def test_repeated_failures_are_blocked(self, client) -> None:
        for _ in range(10):
            await client.post(
                "/api/auth/login",
                json={"email": "a@example.com", "password": "wrong-password"},
            )

        response = await client.post(
            "/api/auth/login",
            json={"email": "a@example.com", "password": "wrong-password"},
        )

        assert response.status_code == 429

    async def test_tells_when_to_retry(self, client) -> None:
        """언제 다시 오면 되는지 알려주지 않으면 계속 두드린다."""
        for _ in range(11):
            response = await client.post(
                "/api/auth/login",
                json={"email": "a@example.com", "password": "wrong"},
            )

        assert response.headers["Retry-After"].isdigit()

    async def test_other_accounts_are_unaffected(self, client, app) -> None:
        """한 계정을 노린 공격이 다른 사람의 로그인을 막으면 안 된다."""
        async with app.state.sessionmaker() as session:
            session.add(
                User(email="b@example.com", password_hash=hash_password(PASSWORD))
            )
            await session.commit()

        for _ in range(11):
            await client.post(
                "/api/auth/login",
                json={"email": "a@example.com", "password": "wrong"},
            )

        response = await client.post(
            "/api/auth/login",
            json={"email": "b@example.com", "password": PASSWORD},
        )

        assert response.status_code == 200

    async def test_unknown_accounts_are_counted_too(self, client) -> None:
        """없는 계정만 빨리 거절하면 그 차이로 가입 여부가 드러난다."""
        for _ in range(10):
            await client.post(
                "/api/auth/login",
                json={"email": "nobody@example.com", "password": "wrong"},
            )

        response = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
        )

        assert response.status_code == 429


class TestSharedAddress:
    async def test_a_labful_of_people_can_all_log_in(self, client, app) -> None:
        """같은 NAT 뒤에서 정원만큼 로그인해도 IP 한도에 걸리면 안 된다.

        처음 잡았던 10회/분 한도에서 실제로 걸렸던 경우다.
        """
        async with app.state.sessionmaker() as session:
            for i in range(10):
                session.add(
                    User(
                        email=f"member{i}@example.com",
                        password_hash=hash_password(PASSWORD),
                    )
                )
            await session.commit()

        statuses = []
        for i in range(10):
            response = await client.post(
                "/api/auth/login",
                json={"email": f"member{i}@example.com", "password": PASSWORD},
            )
            statuses.append(response.status_code)

        assert 429 not in statuses


class TestRegistration:
    async def test_invite_guessing_is_blocked(self, client) -> None:
        """초대 코드를 무한히 넣어볼 수 있으면 초대 제도가 무의미해진다."""
        for _ in range(5):
            await client.post(
                "/api/auth/register",
                json={
                    "email": "x@example.com",
                    "password": PASSWORD,
                    "invite_code": "찍어보기",
                },
            )

        response = await client.post(
            "/api/auth/register",
            json={
                "email": "x@example.com",
                "password": PASSWORD,
                "invite_code": "찍어보기",
            },
        )

        assert response.status_code == 429


class TestNormalUseIsUnaffected:
    async def test_a_real_signup_and_login_work(self, client, app) -> None:
        code = await fresh_invite_code(app.state.sessionmaker)

        registered = await client.post(
            "/api/auth/register",
            json={
                "email": "new@example.com",
                "password": PASSWORD,
                "invite_code": code,
            },
        )
        logged_in = await client.post(
            "/api/auth/login",
            json={"email": "new@example.com", "password": PASSWORD},
        )

        assert registered.status_code == 201
        assert logged_in.status_code == 200


class TestForwardedHeaders:
    async def test_client_key_ignores_spoofable_headers(self) -> None:
        """X-Forwarded-For 를 믿으면 값을 바꿔가며 한도를 무한히 우회한다."""

        class FakeRequest:
            headers = {"X-Forwarded-For": "1.1.1.1"}

            class client:
                host = "10.0.0.5"

        assert throttle.client_key(FakeRequest()) == "10.0.0.5"
