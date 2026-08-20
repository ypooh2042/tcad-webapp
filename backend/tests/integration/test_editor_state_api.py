"""편집기 상태 보관.

세션은 30분 유휴로 끊긴다. 다시 들어왔을 때 빈 화면이면 어느 파일을 보고
있었는지, 어디까지 고쳤는지 사용자가 기억해서 되짚어야 한다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth, routes_editor, routes_files
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.db.models import Base
from tests.helpers import register

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
STATE_URL = "/api/editor/state"


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

    application = FastAPI()
    application.include_router(routes_auth.router, prefix="/api")
    application.include_router(routes_files.router, prefix="/api")
    application.include_router(routes_editor.router, prefix="/api")
    application.state.settings = Settings(
        session_cookie_secure=False, workspaces_root=tmp_path
    )
    application.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    application.state.session_store = InMemorySessionStore()
    application.state.session_policy = SessionPolicy()

    yield application
    await engine.dispose()


async def login_as(app, email: str) -> AsyncClient:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await register(client, app.state.sessionmaker, email, PASSWORD)
    await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    return client


@pytest.fixture
async def alice(app):
    client = await login_as(app, "alice@example.com")
    # 작업공간이 생기며 예제가 들어간다. 탭이 가리킬 파일이 하나 필요하다.
    await client.get("/api/files")
    yield client
    await client.aclose()


@pytest.fixture
async def bob(app):
    client = await login_as(app, "bob@example.com")
    await client.get("/api/files")
    yield client
    await client.aclose()


class TestAuthentication:
    async def test_requires_login_to_read(self, app) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as anonymous:
            assert (await anonymous.get(STATE_URL)).status_code == 401

    async def test_requires_login_to_write(self, app) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as anonymous:
            response = await anonymous.put(STATE_URL, json={"tabs": [], "active": None})
            assert response.status_code == 401


class TestRoundTrip:
    async def test_new_user_has_nothing_open(self, alice) -> None:
        assert (await alice.get(STATE_URL)).json() == {"tabs": [], "active": None}

    async def test_remembers_open_tabs(self, alice) -> None:
        await alice.put(
            STATE_URL,
            json={
                "tabs": [{"path": "nmos.in", "draft": None, "cursor": None}],
                "active": "nmos.in",
            },
        )

        body = (await alice.get(STATE_URL)).json()

        assert body["active"] == "nmos.in"
        assert [tab["path"] for tab in body["tabs"]] == ["nmos.in"]

    async def test_remembers_the_cursor(self, alice) -> None:
        """어디를 보고 있었는지까지 돌아와야 스크롤을 다시 찾지 않는다."""
        await alice.put(
            STATE_URL,
            json={
                "tabs": [
                    {
                        "path": "nmos.in",
                        "draft": None,
                        "cursor": {"line": 42, "column": 7},
                    }
                ],
                "active": "nmos.in",
            },
        )

        tab = (await alice.get(STATE_URL)).json()["tabs"][0]

        assert tab["cursor"] == {"line": 42, "column": 7}

    async def test_remembers_unsaved_edits(self, alice) -> None:
        """저장하지 않은 편집이 세션 만료로 사라지면 안 된다."""
        await alice.put(
            STATE_URL,
            json={
                "tabs": [{"path": "nmos.in", "draft": "고치던 중\n", "cursor": None}],
                "active": "nmos.in",
            },
        )

        assert (await alice.get(STATE_URL)).json()["tabs"][0]["draft"] == "고치던 중\n"

    async def test_overwrites_rather_than_appends(self, alice) -> None:
        await alice.put(
            STATE_URL,
            json={"tabs": [{"path": "nmos.in"}], "active": "nmos.in"},
        )
        await alice.put(STATE_URL, json={"tabs": [], "active": None})

        assert (await alice.get(STATE_URL)).json() == {"tabs": [], "active": None}


class TestIsolation:
    async def test_each_user_has_their_own(self, alice, bob) -> None:
        await alice.put(
            STATE_URL, json={"tabs": [{"path": "nmos.in"}], "active": "nmos.in"}
        )

        assert (await bob.get(STATE_URL)).json() == {"tabs": [], "active": None}


class TestStaleEntries:
    async def test_drops_tabs_for_files_that_no_longer_exist(self, alice) -> None:
        """지운 파일의 탭이 남으면 열 때마다 실패한다."""
        await alice.put(
            STATE_URL,
            json={
                "tabs": [{"path": "nmos.in"}, {"path": "gone.in"}],
                "active": "gone.in",
            },
        )

        body = (await alice.get(STATE_URL)).json()

        assert [tab["path"] for tab in body["tabs"]] == ["nmos.in"]
        # 활성 탭이 사라졌으면 남은 것 중 하나를 가리켜야 한다.
        assert body["active"] == "nmos.in"

    async def test_everything_gone_leaves_an_empty_state(self, alice) -> None:
        await alice.put(
            STATE_URL, json={"tabs": [{"path": "gone.in"}], "active": "gone.in"}
        )

        assert (await alice.get(STATE_URL)).json() == {"tabs": [], "active": None}


class TestLimits:
    async def test_rejects_too_many_tabs(self, alice) -> None:
        # 상한이 없으면 한 요청으로 DB 한 행을 무한히 키울 수 있다.
        response = await alice.put(
            STATE_URL,
            json={"tabs": [{"path": f"f{i}.in"} for i in range(100)], "active": None},
        )

        assert response.status_code == 422

    async def test_rejects_an_oversized_draft(self, alice) -> None:
        response = await alice.put(
            STATE_URL,
            json={
                "tabs": [{"path": "nmos.in", "draft": "x" * 300_000}],
                "active": "nmos.in",
            },
        )

        assert response.status_code == 422

    async def test_active_outside_the_tabs_is_dropped(self, alice) -> None:
        """열려 있지도 않은 탭을 활성으로 두면 화면이 빈 편집기를 띄운다."""
        await alice.put(
            STATE_URL, json={"tabs": [{"path": "nmos.in"}], "active": "other.in"}
        )

        assert (await alice.get(STATE_URL)).json()["active"] == "nmos.in"
