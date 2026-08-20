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


#: 이 앱 인스턴스의 동시 접속 정원. 숫자를 테스트에 박아 두면 정원을 바꿀 때
#: 여기만 옛 값으로 남아 통과한다.
CAP = SessionPolicy().max_concurrent


async def fill_every_slot(app) -> None:
    """정원을 일반 사용자로 가득 채운다.

    계정은 DB 에 직접 심는다. HTTP 로 그만큼 가입하면 가입 빈도 제한에 먼저
    걸리는데, 여기서 보려는 것은 **세션 정원**이다.
    """
    transport = ASGITransport(app=app)
    await seed_users(app, CAP)
    for i in range(CAP):
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as user_client:
            response = await user_client.post(
                "/api/auth/login",
                json={"email": f"user{i}@example.com", "password": PASSWORD},
            )
            assert response.status_code == 200, response.text


class TestConcurrentLimitOverHttp:
    async def test_one_past_the_cap_is_refused(self, app_and_state) -> None:
        """정원이 차면 503 으로 거절한다."""
        await fill_every_slot(app_and_state)
        await seed_users_named(app_and_state, "extra@example.com", role="user")

        async with AsyncClient(
            transport=ASGITransport(app=app_and_state), base_url="http://test"
        ) as extra_client:
            response = await extra_client.post(
                "/api/auth/login",
                json={"email": "extra@example.com", "password": PASSWORD},
            )

        assert response.status_code == 503
        assert "정원" in response.json()["detail"]

    async def test_admin_gets_in_even_when_full(self, app_and_state) -> None:
        """관리자는 정원 밖이다. 가득 찼을 때 들어갈 수 없으면 손쓸 방법이 없다."""
        await fill_every_slot(app_and_state)
        await make_admin(app_and_state, "root@example.com")

        async with AsyncClient(
            transport=ASGITransport(app=app_and_state), base_url="http://test"
        ) as admin_client:
            response = await admin_client.post(
                "/api/auth/login",
                json={"email": "root@example.com", "password": PASSWORD},
            )

        assert response.status_code == 200

    async def test_admin_does_not_take_a_slot_from_users(
        self, app_and_state
    ) -> None:
        """관리자가 먼저 들어와 있어도 일반 사용자 정원은 그대로여야 한다."""
        await make_admin(app_and_state, "root@example.com")
        async with AsyncClient(
            transport=ASGITransport(app=app_and_state), base_url="http://test"
        ) as admin_client:
            await admin_client.post(
                "/api/auth/login",
                json={"email": "root@example.com", "password": PASSWORD},
            )

        await fill_every_slot(app_and_state)


class TestOccupancyEndpoint:
    """지금 몇 명이 쓰고 있는지.

    503 을 받고 나서야 정원이 찼다는 것을 아는 것과, 들어오기 전에 알 수 있는
    것은 다르다.
    """

    async def test_requires_login(self, client) -> None:
        assert (await client.get("/api/auth/occupancy")).status_code == 401

    async def test_reports_capacity_and_occupancy(self, client) -> None:
        await register(client, "a@example.com")
        await login(client, "a@example.com")

        body = (await client.get("/api/auth/occupancy")).json()

        assert body == {"occupied": 1, "capacity": CAP, "admins": 0}

    async def test_admin_is_not_counted_in_the_cap(
        self, client, app_and_state
    ) -> None:
        await make_admin(app_and_state, "root@example.com")
        await login(client, "root@example.com")

        body = (await client.get("/api/auth/occupancy")).json()

        assert body["occupied"] == 0
        assert body["admins"] == 1

    async def test_matches_what_the_login_gate_allows(self, app_and_state) -> None:
        """현황이 "가득참"이라고 말하면 실제로 거절되어야 한다.

        두 곳이 따로 세면 화면이 자리가 있다고 말한 순간 서버가 거절한다.
        """
        await fill_every_slot(app_and_state)
        await seed_users_named(app_and_state, "extra@example.com", role="user")
        await make_admin(app_and_state, "root@example.com")

        transport = ASGITransport(app=app_and_state)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as admin_client:
            await admin_client.post(
                "/api/auth/login",
                json={"email": "root@example.com", "password": PASSWORD},
            )
            body = (await admin_client.get("/api/auth/occupancy")).json()

        assert body["occupied"] == body["capacity"]

        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as extra_client:
            refused = await extra_client.post(
                "/api/auth/login",
                json={"email": "extra@example.com", "password": PASSWORD},
            )
        assert refused.status_code == 503


async def seed_users_named(app, email: str, role: str = "user") -> None:
    """계정 하나를 DB 에 직접 만든다."""
    async with app.state.sessionmaker() as session:
        session.add(
            User(email=email, password_hash=hash_password(PASSWORD), role=role)
        )
        await session.commit()


async def make_admin(app, email: str) -> None:
    """관리자 계정을 DB 에 직접 만든다. 승격 경로는 여기서 검증 대상이 아니다."""
    async with app.state.sessionmaker() as session:
        session.add(
            User(
                email=email,
                password_hash=hash_password(PASSWORD),
                role="admin",
            )
        )
        await session.commit()


async def login(client, email: str):
    return await client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )


def max_age_of(response) -> int | None:
    """세션 쿠키의 max-age. 없으면 브라우저를 닫을 때까지 사는 세션 쿠키다.

    **Set-Cookie 는 여러 번 나갈 수 있다.** 의존성이 갱신용으로 한 번 심고
    로그아웃이 지우는 식이다. 브라우저는 순서대로 적용하므로 마지막 것이 최종
    상태다 — 첫 번째를 읽으면 지운 뒤에도 살아 있다고 잘못 읽는다.
    """
    headers = [
        value
        for key, value in response.headers.multi_items()
        if key.lower() == "set-cookie" and value.startswith("tcad_session=")
    ]
    assert headers, "세션 쿠키가 나가지 않았습니다"
    for part in headers[-1].split(";"):
        name, _, value = part.strip().partition("=")
        if name.lower() == "max-age":
            return int(value)
    return None


class TestCookieLifetime:
    """쿠키가 사는 기간.

    서버가 세션을 살려 둬도 **브라우저가 쿠키를 버리면 로그아웃된 것과 같다.**
    관리자는 유휴 만료를 면제받는데 쿠키만 30분짜리로 나가고 있었고, 그래서
    30분마다 다시 로그인해야 했다.
    """

    async def test_admin_cookie_outlives_the_idle_timeout(
        self, client, app_and_state
    ) -> None:
        await make_admin(app_and_state, "root@example.com")

        response = await login(client, "root@example.com")

        idle = int(SessionPolicy().idle_timeout.total_seconds())
        assert max_age_of(response) is None or max_age_of(response) > idle

    async def test_user_cookie_matches_the_idle_timeout(self, client) -> None:
        # 일반 사용자는 유휴 상한이 곧 세션 수명이다.
        await register(client, "a@example.com")

        response = await login(client, "a@example.com")

        assert max_age_of(response) == int(
            SessionPolicy().idle_timeout.total_seconds()
        )

    async def test_activity_extends_the_user_cookie(self, client) -> None:
        """움직이는 동안에는 쫓겨나지 않아야 한다.

        서버는 요청마다 활동 시각을 미루는데 쿠키는 로그인 시점에 한 번만
        나갔다. 그래서 계속 쓰고 있어도 로그인 30분 뒤에 딱 끊겼다.
        """
        await register(client, "b@example.com")
        await login(client, "b@example.com")

        response = await client.get("/api/auth/me")

        assert response.status_code == 200
        assert max_age_of(response) == int(
            SessionPolicy().idle_timeout.total_seconds()
        )

    async def test_logout_still_clears_the_cookie(self, client) -> None:
        """요청마다 쿠키를 다시 심게 되면서 생긴 위험.

        의존성이 먼저 쿠키를 심고 그 다음 로그아웃이 지운다. 순서가 뒤집히면
        로그아웃해도 브라우저에 세션이 남는다.
        """
        await register(client, "c@example.com")
        await login(client, "c@example.com")

        response = await client.post("/api/auth/logout")

        assert response.status_code == 204
        # 지우는 쪽이 마지막이어야 한다.
        assert max_age_of(response) == 0
        assert (await client.get("/api/auth/me")).status_code == 401
