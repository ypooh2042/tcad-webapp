"""시각화 API.

산출물에는 사용자가 쓴 코드의 실행 결과가 들어 있다. 소유권 격리가 여기서도
지켜져야 하고, 그 판정은 잡 조회와 **같은 404** 여야 한다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth, routes_jobs, routes_plot, routes_projects
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.db.models import Artifact, Base, Job, JobStatus
from app.jobs.queue import JobQueue
from pathlib import Path

from tests.helpers import register

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


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
    for router in (
        routes_auth.router,
        routes_projects.router,
        routes_jobs.router,
        routes_plot.router,
    ):
        application.include_router(router, prefix="/api")
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
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await register(client, app.state.sessionmaker, email, PASSWORD)
    await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    return client


async def seed_job(app, client, fixture: str, tmp_path) -> int:
    """산출물 파일까지 갖춘 완료된 잡을 만든다."""
    project_id = (await client.post("/api/projects", json={"name": fixture})).json()[
        "id"
    ]
    await client.post(
        f"/api/projects/{project_id}/revisions", json={"source": "init\n"}
    )
    job_id = (await client.post(f"/api/projects/{project_id}/jobs")).json()["id"]

    destination = tmp_path / f"{fixture}"
    destination.write_text((FIXTURES / fixture).read_text())

    async with app.state.sessionmaker() as session:
        job = await session.get(Job, job_id)
        job.status = JobStatus.SUCCEEDED
        session.add(
            Artifact(
                job_id=job_id,
                filename=fixture,
                path=str(destination),
                size_bytes=destination.stat().st_size,
                sequence=1,
            )
        )
        await session.commit()
    return job_id


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


@pytest.fixture
async def job_1d(app, alice, tmp_path):
    return await seed_job(app, alice, "1d_boron.str", tmp_path)


@pytest.fixture
async def job_2d(app, alice, tmp_path):
    return await seed_job(app, alice, "2d_substrate.str", tmp_path)


@pytest.fixture
async def job_cmos(app, alice, tmp_path):
    """재질이 셋인 2D 구조. 2d_substrate 는 silicon 하나뿐이라 재질 보기를
    검증할 수 없다."""
    return await seed_job(app, alice, "2d_cmos_source.str", tmp_path)


class TestOwnership:
    async def test_other_user_cannot_read_structure(
        self, alice, bob, job_1d
    ) -> None:
        response = await bob.get(f"/api/jobs/{job_1d}/artifacts/1/structure")

        assert response.status_code == 404

    async def test_missing_and_foreign_are_indistinguishable(
        self, alice, bob, job_1d
    ) -> None:
        foreign = await bob.get(f"/api/jobs/{job_1d}/artifacts/1/structure")
        missing = await bob.get("/api/jobs/999999/artifacts/1/structure")

        assert foreign.status_code == missing.status_code
        assert foreign.json() == missing.json()

    async def test_anonymous_is_rejected(self, app, job_1d) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as anon:
            response = await anon.get(f"/api/jobs/{job_1d}/artifacts/1/structure")

        assert response.status_code == 401


class TestSummary:
    async def test_reports_dimension(self, alice, job_1d) -> None:
        body = (await alice.get(f"/api/jobs/{job_1d}/artifacts/1/structure")).json()

        assert body["dimension"] == 1

    async def test_lists_plottable_quantities(self, alice, job_1d) -> None:
        body = (await alice.get(f"/api/jobs/{job_1d}/artifacts/1/structure")).json()

        assert "chem_boron" in body["quantities"]
        assert "net_doping" in body["quantities"]

    async def test_reports_bounds(self, alice, job_1d) -> None:
        body = (await alice.get(f"/api/jobs/{job_1d}/artifacts/1/structure")).json()

        # 증착된 산화막 때문에 x 가 음수까지 간다.
        assert body["bounds"]["x_min"] == pytest.approx(-0.075)
        assert body["bounds"]["x_max"] == pytest.approx(2.0)

    async def test_lists_materials(self, alice, job_1d) -> None:
        body = (await alice.get(f"/api/jobs/{job_1d}/artifacts/1/structure")).json()

        assert body["materials"] == ["oxide", "silicon"]

    async def test_unknown_sequence_is_404(self, alice, job_1d) -> None:
        response = await alice.get(f"/api/jobs/{job_1d}/artifacts/9/structure")

        assert response.status_code == 404

    async def test_deleted_file_is_410(self, alice, job_1d, app) -> None:
        """산출물은 정리될 수 있다. 404 로 답하면 잡 자체가 없는 것처럼 보인다."""
        async with app.state.sessionmaker() as session:
            artifact = await session.get(Artifact, 1)
            Path(artifact.path).unlink()

        response = await alice.get(f"/api/jobs/{job_1d}/artifacts/1/structure")

        assert response.status_code == 410


class TestProfile:
    async def test_returns_depth_and_value(self, alice, job_1d) -> None:
        body = (
            await alice.get(
                f"/api/jobs/{job_1d}/artifacts/1/profile?quantity=chem_boron"
            )
        ).json()

        assert body["points"][0]["depth"] < 0  # 증착층
        assert body["points"][0]["value"] > 0

    async def test_one_dimensional_needs_no_cut(self, alice, job_1d) -> None:
        body = (
            await alice.get(
                f"/api/jobs/{job_1d}/artifacts/1/profile?quantity=chem_boron"
            )
        ).json()

        assert body["cut_x"] is None

    async def test_two_dimensional_requires_a_cut_position(
        self, alice, job_2d
    ) -> None:
        response = await alice.get(
            f"/api/jobs/{job_2d}/artifacts/1/profile?quantity=chem_boron"
        )

        assert response.status_code == 400

    async def test_two_dimensional_cut(self, alice, job_2d) -> None:
        body = (
            await alice.get(
                f"/api/jobs/{job_2d}/artifacts/1/profile"
                "?quantity=chem_boron&x=2.0"
            )
        ).json()

        assert body["cut_x"] == pytest.approx(2.0)
        assert len(body["points"]) > 1

    async def test_unknown_quantity_is_404(self, alice, job_1d) -> None:
        response = await alice.get(
            f"/api/jobs/{job_1d}/artifacts/1/profile?quantity=chem_gallium"
        )

        assert response.status_code == 404
        # 무엇을 쓸 수 있는지 알려줘야 화면이 다시 물어볼 수 있다.
        assert "chem_boron" in response.json()["detail"]

    async def test_computed_net_doping_is_available(self, alice, job_1d) -> None:
        """저장 컬럼이 없어도 활성 농도로 계산할 수 있다."""
        response = await alice.get(
            f"/api/jobs/{job_1d}/artifacts/1/profile?quantity=net_doping"
        )

        assert response.status_code == 200


class TestSurface:
    async def test_returns_triangles_and_values(self, alice, job_2d) -> None:
        body = (
            await alice.get(
                f"/api/jobs/{job_2d}/artifacts/1/surface?quantity=chem_boron"
            )
        ).json()

        assert len(body["triangles"]) == len(body["values"])
        assert len(body["triangles"][0]) == 3

    async def test_values_are_per_triangle(self, alice, job_2d) -> None:
        body = (
            await alice.get(
                f"/api/jobs/{job_2d}/artifacts/1/surface?quantity=chem_boron"
            )
        ).json()

        assert all(len(triple) == 3 for triple in body["values"])

    async def test_reports_value_range(self, alice, job_2d) -> None:
        body = (
            await alice.get(
                f"/api/jobs/{job_2d}/artifacts/1/surface?quantity=chem_boron"
            )
        ).json()

        assert body["value_min"] <= body["value_max"]

    async def test_one_dimensional_has_no_surface(self, alice, job_1d) -> None:
        response = await alice.get(
            f"/api/jobs/{job_1d}/artifacts/1/surface?quantity=chem_boron"
        )

        assert response.status_code == 400


class TestMaterialSurface:
    """재질만 보는 단면. quantity 를 빼면 재질만 내려온다."""

    async def test_omitting_quantity_gives_materials(self, alice, job_cmos):
        response = await alice.get(
            f"/api/jobs/{job_cmos}/artifacts/1/surface"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["quantity"] == ""
        assert set(body["materials"]) == {"oxide", "poly", "silicon"}

    async def test_carries_no_values(self, alice, job_cmos):
        # 값이 없다. 0 을 채워 보내면 프론트가 색 범위를 잘못 잡는다.
        response = await alice.get(
            f"/api/jobs/{job_cmos}/artifacts/1/surface"
        )

        assert response.json()["values"] == []

    async def test_covers_more_triangles_than_a_quantity_view(
        self, alice, job_cmos
    ):
        """재질 보기는 요소를 버리지 않는다. 적으면 층이 사라진 것이다."""
        materials = await alice.get(f"/api/jobs/{job_cmos}/artifacts/1/surface")
        values = await alice.get(
            f"/api/jobs/{job_cmos}/artifacts/1/surface?quantity=chem_boron"
        )

        assert len(materials.json()["triangles"]) >= len(
            values.json()["triangles"]
        )

    async def test_still_refuses_1d(self, alice, job_1d):
        response = await alice.get(f"/api/jobs/{job_1d}/artifacts/1/surface")

        assert response.status_code == 400

    async def test_unknown_quantity_is_still_rejected(self, alice, job_cmos):
        # 생략 허용이 오타까지 통과시키면 안 된다. 없는 물리량은 404 다
        # (다른 엔드포인트와 같은 규약).
        response = await alice.get(
            f"/api/jobs/{job_cmos}/artifacts/1/surface?quantity=nonexistent"
        )

        assert response.status_code == 404
