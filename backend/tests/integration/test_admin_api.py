"""관리자 초대 API.

발급·조회·회수가 관리자에게만 열려 있어야 한다. 일반 사용자가 초대를 찍어낼 수
있으면 초대 제도 자체가 무의미하다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_admin, routes_auth
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.db.models import Base, User
from app.auth.passwords import hash_password
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
    application.include_router(routes_admin.router, prefix="/api")
    application.state.settings = Settings(session_cookie_secure=False)
    application.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    application.state.session_store = InMemorySessionStore()
    application.state.session_policy = SessionPolicy()

    yield application
    await engine.dispose()


async def make_client(app, email: str, role: str) -> AsyncClient:
    """CLI 로 만든 계정처럼 DB 에 직접 심고 로그인한다."""
    async with app.state.sessionmaker() as session:
        session.add(
            User(email=email, password_hash=hash_password(PASSWORD), role=role)
        )
        await session.commit()

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    return client


@pytest.fixture
async def admin(app):
    client = await make_client(app, "admin@example.com", "admin")
    yield client
    await client.aclose()


@pytest.fixture
async def member(app):
    client = await make_client(app, "member@example.com", "user")
    yield client
    await client.aclose()


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("post", "/api/admin/invites"),
            ("get", "/api/admin/invites"),
            ("delete", "/api/admin/invites/1"),
        ],
    )
    async def test_regular_user_is_refused(self, member, method, path) -> None:
        kwargs = {"json": {}} if method == "post" else {}
        response = await getattr(member, method)(path, **kwargs)

        assert response.status_code == 403

    async def test_anonymous_is_refused(self, app) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as anon:
            response = await anon.get("/api/admin/invites")

        assert response.status_code == 401


class TestIssuing:
    async def test_returns_a_usable_code(self, admin, app) -> None:
        issued = (await admin.post("/api/admin/invites", json={})).json()

        registered = await AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ).post(
            "/api/auth/register",
            json={
                "email": "invited@example.com",
                "password": PASSWORD,
                "invite_code": issued["code"],
            },
        )

        assert registered.status_code == 201

    async def test_code_is_shown_only_once(self, admin) -> None:
        """평문은 저장하지 않는다. 다시 볼 수 있으면 DB 유출 시 그대로 쓰인다."""
        issued = (await admin.post("/api/admin/invites", json={})).json()

        listed = (await admin.get("/api/admin/invites")).json()

        assert "code" not in listed[0]
        assert issued["code"] not in (await admin.get("/api/admin/invites")).text

    async def test_defaults_to_single_use_seven_days(self, admin) -> None:
        issued = (await admin.post("/api/admin/invites", json={})).json()

        assert issued["max_uses"] == 1

    async def test_rejects_unbounded_validity(self, admin) -> None:
        """무기한 코드는 사실상 가입 개방과 같다."""
        response = await admin.post("/api/admin/invites", json={"valid_days": 9999})

        assert response.status_code == 422

    async def test_rejects_excessive_uses(self, admin) -> None:
        response = await admin.post("/api/admin/invites", json={"max_uses": 1000})

        assert response.status_code == 422


class TestListing:
    async def test_reports_usage(self, admin, app) -> None:
        issued = (await admin.post("/api/admin/invites", json={"max_uses": 2})).json()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as guest:
            await guest.post(
                "/api/auth/register",
                json={
                    "email": "one@example.com",
                    "password": PASSWORD,
                    "invite_code": issued["code"],
                },
            )

        listed = (await admin.get("/api/admin/invites")).json()
        entry = next(item for item in listed if item["id"] == issued["id"])

        assert entry["used_count"] == 1
        assert entry["usable"] is True


class TestRevoking:
    async def test_revoked_code_stops_working(self, admin, app) -> None:
        """회수는 재배포 없이 즉시 들어야 한다."""
        issued = (await admin.post("/api/admin/invites", json={})).json()

        await admin.delete(f"/api/admin/invites/{issued['id']}")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as guest:
            response = await guest.post(
                "/api/auth/register",
                json={
                    "email": "late@example.com",
                    "password": PASSWORD,
                    "invite_code": issued["code"],
                },
            )

        assert response.status_code == 403
        assert "회수" in response.json()["detail"]

    async def test_history_is_kept(self, admin) -> None:
        """행을 지우면 누가 발급했는지가 사라진다."""
        issued = (await admin.post("/api/admin/invites", json={})).json()

        await admin.delete(f"/api/admin/invites/{issued['id']}")
        listed = (await admin.get("/api/admin/invites")).json()

        entry = next(item for item in listed if item["id"] == issued["id"])
        assert entry["revoked"] is True
        assert entry["usable"] is False

    async def test_double_revoke_is_404(self, admin) -> None:
        issued = (await admin.post("/api/admin/invites", json={})).json()
        await admin.delete(f"/api/admin/invites/{issued['id']}")

        response = await admin.delete(f"/api/admin/invites/{issued['id']}")

        assert response.status_code == 404


class TestRegistrationRequiresInvite:
    async def test_missing_invite_is_rejected(self, app) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as guest:
            response = await guest.post(
                "/api/auth/register",
                json={"email": "nobody@example.com", "password": PASSWORD},
            )

        assert response.status_code == 422

    async def test_wrong_invite_is_rejected(self, app) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as guest:
            response = await guest.post(
                "/api/auth/register",
                json={
                    "email": "nobody@example.com",
                    "password": PASSWORD,
                    "invite_code": "아무거나",
                },
            )

        assert response.status_code == 403

    async def test_valid_invite_is_accepted(self, app) -> None:
        code = await fresh_invite_code(app.state.sessionmaker)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as guest:
            response = await guest.post(
                "/api/auth/register",
                json={
                    "email": "ok@example.com",
                    "password": PASSWORD,
                    "invite_code": code,
                },
            )

        assert response.status_code == 201
