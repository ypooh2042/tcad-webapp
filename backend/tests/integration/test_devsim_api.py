"""소자 해석 API.

화면이 `.str` 을 직접 읽지 않는다. 전극을 찾는 것도, 스펙이 말이 되는지 보는
것도 서버가 한다 — 파서를 두 벌 유지하지 않기 위해서고, 워커까지 가서야 오타를
알게 되면 사용자가 몇 분을 버리기 때문이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth, routes_devsim
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.db.models import Artifact, Base, DevSimResult, Job, JobKind, JobStatus, User
from app.jobs.queue import JobQueue
from tests.helpers import register

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
FIXTURES = Path(__file__).parent.parent / "fixtures"


def spec_body(**overrides) -> dict:
    body = {
        "label": "기본 조건",
        "electrodes": [
            {"origin": "detected", "key": "source", "label": "S"},
            {"origin": "detected", "key": "gate", "label": "G"},
            {"origin": "detected", "key": "drain", "label": "D"},
            {"origin": "backside", "label": "B"},
        ],
        "biases": [
            {"name": "Vs", "electrodes": ["S", "B"], "role": "const", "value": 0.0},
            {"name": "Vg", "electrodes": ["G"], "role": "step", "values": [0.0, 1.0]},
            {
                "name": "Vd",
                "electrodes": ["D"],
                "role": "sweep",
                "sweep": {"start": 0.0, "stop": 1.0, "step": 0.5},
            },
        ],
    }
    body.update(overrides)
    return body


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
    application.include_router(routes_devsim.router, prefix="/api")
    application.state.settings = Settings(
        session_cookie_secure=False, jobs_root=tmp_path / "jobs"
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
    async with app.state.sessionmaker() as session:
        return (await session.execute(select(User.id))).scalars().first()


@pytest.fixture
async def structure_job(app, tmp_path):
    """알루미늄 전극이 있는 구조를 산출물로 가진 잡."""
    workdir = tmp_path / "source-job"
    workdir.mkdir()
    target = workdir / "contacts.str"
    target.write_text((FIXTURES / "2d_contacts.str").read_text())

    async with app.state.sessionmaker() as session:
        job = Job(
            owner_id=await owner_id(app),
            source_path="contacts.in",
            source="init boron conc=1e15\n",
            status=JobStatus.SUCCEEDED,
            workdir=str(workdir),
        )
        session.add(job)
        await session.flush()
        session.add(
            Artifact(
                job_id=job.id,
                filename=target.name,
                path=str(target),
                size_bytes=target.stat().st_size,
                sequence=1,
            )
        )
        await session.commit()
        return job.id


class TestElectrodes:
    async def test_finds_source_gate_drain_and_backside(
        self, client, structure_job
    ) -> None:
        response = await client.get(
            f"/api/devsim/jobs/{structure_job}/artifacts/1/electrodes"
        )
        assert response.status_code == 200
        body = response.json()
        assert [e["key"] for e in body["electrodes"]] == [
            "source",
            "gate",
            "drain",
            "body",
        ]

    def _by_key(self, body: dict) -> dict:
        return {e["key"]: e for e in body["electrodes"]}

    async def test_reports_where_each_electrode_sits(
        self, client, structure_job
    ) -> None:
        body = (
            await client.get(
                f"/api/devsim/jobs/{structure_job}/artifacts/1/electrodes"
            )
        ).json()
        found = self._by_key(body)
        assert found["gate"]["materials"] == ["poly"]
        assert found["source"]["extent"]["x_max"] <= found["gate"]["extent"]["x_min"]
        assert found["body"]["origin"] == "backside"

    async def test_gives_segments_to_draw(self, client, structure_job) -> None:
        body = (
            await client.get(
                f"/api/devsim/jobs/{structure_job}/artifacts/1/electrodes"
            )
        ).json()
        for electrode in body["electrodes"]:
            assert electrode["segments"]
            assert all(len(segment) == 4 for segment in electrode["segments"])
            assert electrode["edge_count"] == len(electrode["segments"])

    async def test_conductor_mode_changes_the_gate(
        self, client, structure_job
    ) -> None:
        body = (
            await client.get(
                f"/api/devsim/jobs/{structure_job}/artifacts/1/electrodes",
                params={"gate_model": "conductor"},
            )
        ).json()
        assert body["gate_model"] == "conductor"
        assert self._by_key(body)["gate"]["kind"] == "insulator"

    async def test_someone_elses_job_is_not_found(self, app, client, tmp_path) -> None:
        async with app.state.sessionmaker() as session:
            other = User(
                email="bob@example.com", password_hash="x", role="user"
            )
            session.add(other)
            await session.flush()
            job = Job(
                owner_id=other.id,
                status=JobStatus.SUCCEEDED,
                workdir=str(tmp_path / "other"),
            )
            session.add(job)
            await session.commit()
            stolen = job.id

        response = await client.get(
            f"/api/devsim/jobs/{stolen}/artifacts/1/electrodes"
        )
        # 403 이면 남의 잡이 존재한다는 사실이 새어 나간다.
        assert response.status_code == 404


class TestSubmit:
    async def test_queues_a_devsim_job(self, app, client, structure_job) -> None:
        response = await client.post(
            "/api/devsim/jobs",
            json={"job_id": structure_job, "sequence": 1, "spec": spec_body()},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "queued"
        assert body["total_points"] == 6

        async with app.state.sessionmaker() as session:
            job = await session.get(Job, body["id"])
            assert job.kind == JobKind.DEVSIM

    async def test_copies_the_structure_into_the_job_directory(
        self, app, client, structure_job
    ) -> None:
        """원본 잡의 산출물은 청소에 지워질 수 있다. 입력 스냅샷이 필요하다."""
        body = (
            await client.post(
                "/api/devsim/jobs",
                json={"job_id": structure_job, "sequence": 1, "spec": spec_body()},
            )
        ).json()
        async with app.state.sessionmaker() as session:
            job = await session.get(Job, body["id"])
        copied = Path(job.workdir) / "structure.str"
        assert copied.exists()
        assert copied.read_text() == (FIXTURES / "2d_contacts.str").read_text()

    async def test_records_which_structure_it_came_from(
        self, app, client, structure_job
    ) -> None:
        body = (
            await client.post(
                "/api/devsim/jobs",
                json={"job_id": structure_job, "sequence": 1, "spec": spec_body()},
            )
        ).json()
        async with app.state.sessionmaker() as session:
            job = await session.get(Job, body["id"])
        assert json.loads(job.source)["structure"] == "contacts.str"

    async def test_the_client_cannot_forge_the_structure_name(
        self, app, client, structure_job
    ) -> None:
        body = (
            await client.post(
                "/api/devsim/jobs",
                json={
                    "job_id": structure_job,
                    "sequence": 1,
                    "spec": spec_body(structure="어딘가 다른 곳.str"),
                },
            )
        ).json()
        async with app.state.sessionmaker() as session:
            job = await session.get(Job, body["id"])
        assert json.loads(job.source)["structure"] == "contacts.str"

    async def test_rejects_an_electrode_that_is_not_there(
        self, client, structure_job
    ) -> None:
        spec = spec_body()
        spec["electrodes"][0]["key"] = "collector"
        response = await client.post(
            "/api/devsim/jobs",
            json={"job_id": structure_job, "sequence": 1, "spec": spec},
        )
        assert response.status_code == 422
        assert "collector" in response.json()["detail"]

    async def test_rejects_a_spec_with_two_sweeps(
        self, client, structure_job
    ) -> None:
        spec = spec_body()
        spec["biases"][1]["role"] = "sweep"
        spec["biases"][1]["sweep"] = {"start": 0.0, "stop": 1.0, "step": 0.5}
        response = await client.post(
            "/api/devsim/jobs",
            json={"job_id": structure_job, "sequence": 1, "spec": spec},
        )
        assert response.status_code == 422

    async def test_rejects_too_many_bias_points(
        self, client, structure_job
    ) -> None:
        spec = spec_body()
        spec["biases"][2]["sweep"] = {"start": 0.0, "stop": 90.0, "step": 0.5}
        spec["biases"][1]["values"] = [float(v) for v in range(8)]
        response = await client.post(
            "/api/devsim/jobs",
            json={"job_id": structure_job, "sequence": 1, "spec": spec},
        )
        assert response.status_code == 422

    async def test_missing_artifact_is_not_found(self, client, structure_job) -> None:
        response = await client.post(
            "/api/devsim/jobs",
            json={"job_id": structure_job, "sequence": 99, "spec": spec_body()},
        )
        assert response.status_code == 404


class TestRuns:
    async def _store(self, app, label: str, completed: int) -> int:
        async with app.state.sessionmaker() as session:
            job = Job(
                owner_id=await owner_id(app),
                kind=JobKind.DEVSIM,
                status=JobStatus.SUCCEEDED,
                workdir="/tmp/none",
            )
            session.add(job)
            await session.flush()
            session.add(
                DevSimResult(
                    job_id=job.id,
                    owner_id=job.owner_id,
                    label=label,
                    structure="contacts.str",
                    spec=json.dumps(spec_body()),
                    data=json.dumps(
                        {"completed": completed, "total": 6, "rows": []}
                    ),
                )
            )
            await session.commit()
            return job.id

    async def test_lists_my_runs(self, app, client) -> None:
        await self._store(app, "첫 번째", 6)
        await self._store(app, "두 번째", 3)
        body = (await client.get("/api/devsim/runs")).json()
        assert {row["label"] for row in body} == {"첫 번째", "두 번째"}

    async def test_returns_the_curve_and_the_conditions(self, app, client) -> None:
        job_id = await self._store(app, "첫 번째", 6)
        body = (await client.get(f"/api/devsim/runs/{job_id}")).json()
        assert body["completed"] == 6
        assert body["data"]["total"] == 6
        # 비교 화면이 "무엇이 달랐나"를 보여주려면 조건이 함께 와야 한다.
        assert body["spec"]["label"] == "기본 조건"

    async def test_a_job_without_a_result_is_not_found(
        self, app, client, structure_job
    ) -> None:
        response = await client.get(f"/api/devsim/runs/{structure_job}")
        assert response.status_code == 404


class TestStructures:
    """DevSim 탭을 바로 열었을 때 고를 구조 목록.

    공정 결과에서 "소자 해석" 버튼으로 넘어오는 것이 주 경로지만, 탭을 직접
    열 수도 있어야 한다. `.str` 은 작업공간 파일 목록에 안 나오므로
    (`app/workspace/service.py`) 잡 산출물에서 뽑아 준다.
    """

    async def test_lists_structures_from_my_runs(
        self, client, structure_job
    ) -> None:
        body = (await client.get("/api/devsim/structures")).json()
        assert len(body) == 1
        entry = body[0]
        assert entry["job_id"] == structure_job
        assert entry["source_path"] == "contacts.in"
        assert entry["artifacts"] == [
            {"sequence": 1, "filename": "contacts.str"}
        ]

    async def test_devsim_jobs_are_not_offered_as_input(
        self, app, client, structure_job
    ) -> None:
        """해석 결과(`iv.json`)를 다시 해석할 수는 없다."""
        async with app.state.sessionmaker() as session:
            job = Job(
                owner_id=await owner_id(app),
                kind=JobKind.DEVSIM,
                status=JobStatus.SUCCEEDED,
                workdir="/tmp/none",
            )
            session.add(job)
            await session.flush()
            session.add(
                Artifact(
                    job_id=job.id,
                    filename="iv.json",
                    path="/tmp/none/iv.json",
                    size_bytes=10,
                    sequence=1,
                )
            )
            await session.commit()

        body = (await client.get("/api/devsim/structures")).json()
        assert [entry["job_id"] for entry in body] == [structure_job]

    async def test_failed_runs_are_not_offered(
        self, app, client, structure_job
    ) -> None:
        async with app.state.sessionmaker() as session:
            job = Job(
                owner_id=await owner_id(app),
                status=JobStatus.FAILED,
                workdir="/tmp/none",
            )
            session.add(job)
            await session.commit()
        body = (await client.get("/api/devsim/structures")).json()
        assert [entry["job_id"] for entry in body] == [structure_job]
