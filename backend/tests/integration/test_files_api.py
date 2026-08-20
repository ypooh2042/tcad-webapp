"""작업공간 파일 API.

가장 중요한 검증은 **격리**다. 사용자는 자기 루트만 보고, 남의 루트나 서버
파일시스템에는 어떤 경로로도 닿을 수 없어야 한다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth, routes_files, routes_jobs
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.db.models import Base
from app.jobs.queue import JobQueue
from tests.helpers import register

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
async def app(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    application = FastAPI()
    application.include_router(routes_auth.router, prefix="/api")
    application.include_router(routes_files.router, prefix="/api")
    application.include_router(routes_jobs.router, prefix="/api")
    application.state.settings = Settings(
        session_cookie_secure=False,
        workspaces_root=tmp_path / "workspaces",
        workspace_quota_mb=1,
        jobs_root=tmp_path / "jobs",
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    application.state.sessionmaker = maker
    application.state.queue = JobQueue(maker)
    application.state.session_store = InMemorySessionStore()
    application.state.session_policy = SessionPolicy()
    yield application
    await engine.dispose()


async def _login(app, email: str) -> AsyncClient:
    """가입 + 로그인을 마친 클라이언트. 가입만으로는 세션이 붙지 않는다.

    **새 작업공간에 들어 있는 예제는 치우고 시작한다**(app/workspace/starter.py).
    이 파일이 보려는 것은 파일 조작과 격리이므로, 예제가 섞이면 목록 검증이
    전부 그 파일을 달고 다녀야 한다. 예제가 실제로 들어가는지는 아래
    TestStarterExample 과 test_workspace_starter.py 가 본다.
    """
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await register(client, app.state.sessionmaker, email, PASSWORD)
    await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    await client.delete("/api/files?path=nmos.in")
    return client


@pytest.fixture
async def alice(app):
    client = await _login(app, "alice@example.com")
    yield client
    await client.aclose()


@pytest.fixture
async def bob(app):
    client = await _login(app, "bob@example.com")
    yield client
    await client.aclose()


class TestAuthRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/files"),
            ("get", "/api/files/content?path=a.in"),
            ("put", "/api/files/content"),
            ("post", "/api/files/folder"),
            ("post", "/api/files/rename"),
            ("delete", "/api/files?path=a.in"),
            ("get", "/api/files/usage"),
        ],
    )
    async def test_anonymous_is_rejected(self, app, method, path):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as anon:
            # httpx 의 get/delete 는 json= 을 받지 않는다.
            call = getattr(anon, method)
            response = await (
                call(path) if method in ("get", "delete") else call(path, json={})
            )

        assert response.status_code == 401


class TestListing:
    async def test_starts_empty(self, alice):
        response = await alice.get("/api/files")

        assert response.status_code == 200
        assert response.json()["entries"] == []

    async def test_shows_what_was_written(self, alice):
        await alice.put("/api/files/content", json={"path": "a.in", "content": "x"})

        entries = (await alice.get("/api/files")).json()["entries"]

        assert [e["path"] for e in entries] == ["a.in"]

    async def test_walks_every_level(self, alice):
        await alice.post("/api/files/folder", json={"path": "semi"})
        await alice.put(
            "/api/files/content", json={"path": "semi/b.in", "content": "x"}
        )

        entries = (await alice.get("/api/files")).json()["entries"]

        assert sorted(e["path"] for e in entries) == ["semi", "semi/b.in"]

    async def test_hides_artifacts(self, alice, app):
        # `.str` 은 실행 결과다. 목록에 뜨면 지울 수 있게 되고 혼란스럽다.
        await alice.put("/api/files/content", json={"path": "a.in", "content": "x"})
        root = app.state.settings.workspaces_root
        target = next(root.iterdir())
        (target / "result.str").write_text("x")

        entries = (await alice.get("/api/files")).json()["entries"]

        assert [e["path"] for e in entries] == ["a.in"]


class TestIsolation:
    async def test_users_do_not_see_each_other(self, alice, bob):
        await alice.put(
            "/api/files/content", json={"path": "secret.in", "content": "비밀"}
        )

        entries = (await bob.get("/api/files")).json()["entries"]

        assert entries == []

    async def test_cannot_read_another_users_file(self, alice, bob):
        await alice.put(
            "/api/files/content", json={"path": "secret.in", "content": "비밀"}
        )

        response = await bob.get("/api/files/content?path=secret.in")

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "path",
        ["../user-1/secret.in", "/etc/passwd", "../../etc/passwd", ".."],
    )
    async def test_cannot_climb_out(self, bob, path):
        response = await bob.get(f"/api/files/content?path={path}")

        assert response.status_code in (400, 404)

    async def test_error_never_leaks_a_server_path(self, bob):
        response = await bob.get("/api/files/content?path=../../etc/passwd")

        assert "/home" not in response.text
        assert "workspaces" not in response.text


class TestWrite:
    async def test_creates_and_reads_back(self, alice):
        await alice.put(
            "/api/files/content", json={"path": "a.in", "content": "내용\n"}
        )

        response = await alice.get("/api/files/content?path=a.in")

        assert response.json()["content"] == "내용\n"

    async def test_rejects_a_non_source_extension(self, alice):
        response = await alice.put(
            "/api/files/content", json={"path": "a.txt", "content": "x"}
        )

        assert response.status_code == 400

    async def test_rejects_a_missing_parent(self, alice):
        response = await alice.put(
            "/api/files/content", json={"path": "없다/a.in", "content": "x"}
        )

        assert response.status_code == 404

    async def test_rejects_content_over_the_quota(self, alice):
        """상한은 1MB 로 잡아 둔 픽스처다.

        파일 하나로는 못 넘긴다 — 요청 본문 자체에 20만자 상한이 걸려 있어
        그쪽에서 먼저 422 가 난다. 실제로 문제가 되는 것도 한 방이 아니라
        쌓여서 넘는 경우다.
        """
        chunk = "x" * 190_000
        for index in range(5):
            assert (
                await alice.put(
                    "/api/files/content",
                    json={"path": f"f{index}.in", "content": chunk},
                )
            ).status_code == 200

        response = await alice.put(
            "/api/files/content", json={"path": "over.in", "content": chunk}
        )

        assert response.status_code == 413


class TestFolders:
    async def test_creates_one(self, alice):
        response = await alice.post("/api/files/folder", json={"path": "semi"})

        assert response.status_code == 201
        assert (await alice.get("/api/files")).json()["entries"][0]["is_dir"] is True

    async def test_duplicate_is_a_conflict(self, alice):
        await alice.post("/api/files/folder", json={"path": "semi"})

        response = await alice.post("/api/files/folder", json={"path": "semi"})

        assert response.status_code == 409


class TestRename:
    async def test_renames(self, alice):
        await alice.put("/api/files/content", json={"path": "a.in", "content": "x"})

        response = await alice.post(
            "/api/files/rename", json={"path": "a.in", "destination": "b.in"}
        )

        assert response.status_code == 200
        assert (await alice.get("/api/files/content?path=b.in")).status_code == 200

    async def test_clobbering_is_a_conflict(self, alice):
        await alice.put("/api/files/content", json={"path": "a.in", "content": "A"})
        await alice.put("/api/files/content", json={"path": "b.in", "content": "B"})

        response = await alice.post(
            "/api/files/rename", json={"path": "a.in", "destination": "b.in"}
        )

        assert response.status_code == 409


class TestDelete:
    async def test_deletes_a_file(self, alice):
        await alice.put("/api/files/content", json={"path": "a.in", "content": "x"})

        response = await alice.delete("/api/files?path=a.in")

        assert response.status_code == 204
        assert (await alice.get("/api/files")).json()["entries"] == []

    async def test_deletes_a_folder_and_contents(self, alice):
        await alice.post("/api/files/folder", json={"path": "semi"})
        await alice.put(
            "/api/files/content", json={"path": "semi/a.in", "content": "x"}
        )

        await alice.delete("/api/files?path=semi")

        assert (await alice.get("/api/files")).json()["entries"] == []

    async def test_missing_target_is_404(self, alice):
        response = await alice.delete("/api/files?path=없다.in")

        assert response.status_code == 404


class TestUsage:
    async def test_reports_used_and_limit(self, alice):
        await alice.put(
            "/api/files/content", json={"path": "a.in", "content": "12345"}
        )

        body = (await alice.get("/api/files/usage")).json()

        assert body["used_bytes"] == 5
        assert body["quota_bytes"] == 1024 * 1024


class TestRun:
    """파일을 직접 실행한다. 프로젝트를 거치지 않는다."""

    async def test_submits_the_file(self, alice):
        await alice.put(
            "/api/files/content", json={"path": "a.in", "content": "mode one.dim\n"}
        )

        response = await alice.post("/api/files/jobs", json={"path": "a.in"})

        assert response.status_code == 201
        assert response.json()["status"] == "queued"

    async def test_records_which_file_ran(self, alice):
        await alice.post("/api/files/folder", json={"path": "semi"})
        await alice.put(
            "/api/files/content", json={"path": "semi/a.in", "content": "x"}
        )

        response = await alice.post("/api/files/jobs", json={"path": "semi/a.in"})

        assert response.json()["source_path"] == "semi/a.in"

    async def test_missing_file_is_404(self, alice):
        response = await alice.post("/api/files/jobs", json={"path": "없다.in"})

        assert response.status_code == 404

    async def test_cannot_run_another_users_file(self, alice, bob):
        await alice.put("/api/files/content", json={"path": "a.in", "content": "x"})

        response = await bob.post("/api/files/jobs", json={"path": "a.in"})

        assert response.status_code == 404

    @pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd"])
    async def test_cannot_run_outside_the_workspace(self, alice, path):
        response = await alice.post("/api/files/jobs", json={"path": path})

        assert response.status_code in (400, 404)

    async def test_refuses_a_folder(self, alice):
        await alice.post("/api/files/folder", json={"path": "semi"})

        response = await alice.post("/api/files/jobs", json={"path": "semi"})

        assert response.status_code == 404


class TestJobDetailForFileRuns:
    """파일로 돌린 잡도 조회가 되어야 한다.

    응답 모델이 리비전 id 를 필수로 두면 파일 기반 잡에서 직렬화가 터지고,
    화면은 폴링 실패만 반복한다("연결이 불안정합니다").
    """

    async def test_detail_is_readable(self, alice):
        await alice.put("/api/files/content", json={"path": "a.in", "content": "x"})
        job_id = (
            await alice.post("/api/files/jobs", json={"path": "a.in"})
        ).json()["id"]

        response = await alice.get(f"/api/jobs/{job_id}")

        assert response.status_code == 200
        assert response.json()["source_revision_id"] is None

    async def test_detail_reports_which_file_ran(self, alice):
        await alice.put("/api/files/content", json={"path": "a.in", "content": "x"})
        job_id = (
            await alice.post("/api/files/jobs", json={"path": "a.in"})
        ).json()["id"]

        assert (await alice.get(f"/api/jobs/{job_id}")).json()["source_path"] == "a.in"


class TestJobIdentity:
    """화면은 잡 번호 대신 '무엇을 언제 돌렸는지' 로 실행을 가리킨다.

    번호는 전체 사용자가 공유하는 기본키라 혼자 두 번 돌려도 건너뛴다.
    """

    async def test_detail_reports_when_it_ran(self, alice):
        await alice.put("/api/files/content", json={"path": "a.in", "content": "x"})
        job_id = (
            await alice.post("/api/files/jobs", json={"path": "a.in"})
        ).json()["id"]

        body = (await alice.get(f"/api/jobs/{job_id}")).json()

        assert body["created_at"] is not None
        # 시간대가 없으면 화면이 현지 시각으로 못 바꾼다.
        assert body["created_at"].endswith("Z") or "+" in body["created_at"]


class TestStarterExample:
    """처음 들어온 사람에게 빈 화면을 주지 않는다."""

    async def test_a_new_workspace_has_the_example(self, app) -> None:
        client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )
        await register(client, app.state.sessionmaker, "new@example.com", PASSWORD)
        await client.post(
            "/api/auth/login", json={"email": "new@example.com", "password": PASSWORD}
        )

        entries = (await client.get("/api/files")).json()["entries"]
        await client.aclose()

        assert [entry["name"] for entry in entries] == ["nmos.in"]

    async def test_the_example_can_be_opened_and_run(self, app) -> None:
        """열리지 않는 예제는 없는 것만 못하다."""
        client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )
        await register(client, app.state.sessionmaker, "open@example.com", PASSWORD)
        await client.post(
            "/api/auth/login", json={"email": "open@example.com", "password": PASSWORD}
        )

        content = (await client.get("/api/files/content?path=nmos.in")).json()
        submitted = await client.post("/api/files/jobs", json={"path": "nmos.in"})
        await client.aclose()

        assert "structure out=25_metal_contact.str" in content["content"]
        assert submitted.status_code == 201
