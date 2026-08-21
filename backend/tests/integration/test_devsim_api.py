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
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth, routes_devsim
from app.auth.policy import SessionPolicy
from app.auth.store import InMemorySessionStore
from app.core.config import Settings
from app.db.models import (
    Base,
    DevSimResult,
    Job,
    JobKind,
    JobStatus,
    SavedStructure,
    User,
)
from app.jobs.queue import JobQueue
from tests.helpers import register

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
FIXTURES = Path(__file__).parent.parent / "fixtures"


def spec_body(**overrides) -> dict:
    body = {
        "label": "기본 조건",
        "electrodes": [
            {"label": "S", "interfaces": ["source"]},
            {"label": "G", "interfaces": ["gate"]},
            {"label": "D", "interfaces": ["drain"]},
            {"label": "B", "interfaces": ["body"]},
        ],
        "biases": [
            {"name": "Vs", "electrode": "S", "role": "const", "value": 0.0},
            {"name": "Vb", "electrode": "B", "role": "const", "value": 0.0},
            {"name": "Vg", "electrode": "G", "role": "step", "values": [0.0, 1.0]},
            {
                "name": "Vd",
                "electrode": "D",
                "role": "sweep",
                "sweep": {"start": 0.0, "stop": 1.0, "points": 3},
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


async def clear_seeded(app) -> None:
    """가입할 때 들어간 예제 구조를 걷어낸다.

    새 사용자는 `nmos.in` 예제 구조를 하나 갖고 시작한다(소자 해석 탭이 처음부터
    비어 있지 않도록). 목록을 세는 시험은 그것까지 세면 뜻이 흐려지므로 지운다.
    """
    async with app.state.sessionmaker() as session:
        # 예제만 지운다. 통째로 지우면 시험이 방금 만들어 둔 것까지 사라진다.
        await session.execute(
            delete(SavedStructure).where(SavedStructure.source_path == "nmos.in")
        )
        await session.commit()


async def owner_id(app) -> int:
    async with app.state.sessionmaker() as session:
        return (await session.execute(select(User.id))).scalars().first()


@pytest.fixture
async def saved(app, tmp_path):
    """알루미늄 전극이 있는 보관 구조 하나.

    잡 산출물이 아니라 보관소를 쓴다. 산출물은 스윕에 지워지므로, 공정을 돌린
    다음 날 해석하려면 보관본이 있어야 한다(`app/devsim/catalog.py`).
    """
    return await store_structure(app, tmp_path, "contacts.in", "contacts.str")


async def store_structure(
    app, tmp_path, source_path: str, filename: str, fixture: str = "2d_contacts.str"
) -> int:
    folder = tmp_path / "store" / source_path
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    target.write_text((FIXTURES / fixture).read_text())

    async with app.state.sessionmaker() as session:
        job = Job(
            owner_id=await owner_id(app),
            source_path=source_path,
            source="init boron conc=1e15\n",
            status=JobStatus.SUCCEEDED,
            workdir=str(folder),
        )
        session.add(job)
        await session.flush()
        row = SavedStructure(
            owner_id=job.owner_id,
            source_path=source_path,
            job_id=job.id,
            sequence=1,
            filename=filename,
            path=str(target),
            size_bytes=target.stat().st_size,
        )
        session.add(row)
        await session.commit()
        return row.id


class TestInterfaces:
    async def test_finds_source_gate_drain_and_backside(
        self, client, saved
    ) -> None:
        response = await client.get(
            f"/api/devsim/structures/{saved}/interfaces"
        )
        assert response.status_code == 200
        body = response.json()
        assert [e["key"] for e in body["interfaces"]] == [
            "source",
            "gate",
            "drain",
            "body",
        ]

    def _by_key(self, body: dict) -> dict:
        return {e["key"]: e for e in body["interfaces"]}

    async def test_reports_where_each_electrode_sits(
        self, client, saved
    ) -> None:
        body = (
            await client.get(
                f"/api/devsim/structures/{saved}/interfaces"
            )
        ).json()
        found = self._by_key(body)
        assert found["gate"]["materials"] == ["poly"]
        assert found["source"]["extent"]["x_max"] <= found["gate"]["extent"]["x_min"]
        assert found["body"]["origin"] == "backside"

    async def test_gives_segments_to_draw(self, client, saved) -> None:
        body = (
            await client.get(
                f"/api/devsim/structures/{saved}/interfaces"
            )
        ).json()
        for electrode in body["interfaces"]:
            assert electrode["segments"]
            assert all(len(segment) == 4 for segment in electrode["segments"])
            assert electrode["edge_count"] == len(electrode["segments"])

    async def test_conductor_mode_changes_the_gate(
        self, client, saved
    ) -> None:
        body = (
            await client.get(
                f"/api/devsim/structures/{saved}/interfaces",
                params={"gate_model": "conductor"},
            )
        ).json()
        assert body["gate_model"] == "conductor"
        assert self._by_key(body)["gate"]["kind"] == "insulator"

    async def test_someone_elses_structure_is_not_found(
        self, app, client, tmp_path
    ) -> None:
        async with app.state.sessionmaker() as session:
            other = User(email="bob@example.com", password_hash="x", role="user")
            session.add(other)
            await session.flush()
            row = SavedStructure(
                owner_id=other.id,
                source_path="theirs.in",
                job_id=None,
                sequence=1,
                filename="theirs.str",
                path=str(tmp_path / "theirs.str"),
                size_bytes=10,
            )
            session.add(row)
            await session.commit()
            stolen = row.id

        response = await client.get(f"/api/devsim/structures/{stolen}/interfaces")
        # 403 이면 남의 구조가 존재한다는 사실이 새어 나간다.
        assert response.status_code == 404

    async def test_an_unknown_structure_is_not_found(self, client) -> None:
        assert (
            await client.get("/api/devsim/structures/999999/interfaces")
        ).status_code == 404


class TestSubmit:
    async def test_queues_a_devsim_job(self, app, client, saved) -> None:
        response = await client.post(
            "/api/devsim/jobs",
            json={"structure_id": saved, "spec": spec_body()},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "queued"
        assert body["total_points"] == 6

        async with app.state.sessionmaker() as session:
            job = await session.get(Job, body["id"])
            assert job.kind == JobKind.DEVSIM

    async def test_copies_the_structure_into_the_job_directory(
        self, app, client, saved
    ) -> None:
        """원본 잡의 산출물은 청소에 지워질 수 있다. 입력 스냅샷이 필요하다."""
        body = (
            await client.post(
                "/api/devsim/jobs",
                json={"structure_id": saved, "spec": spec_body()},
            )
        ).json()
        async with app.state.sessionmaker() as session:
            job = await session.get(Job, body["id"])
        copied = Path(job.workdir) / "structure.str"
        assert copied.exists()
        assert copied.read_text() == (FIXTURES / "2d_contacts.str").read_text()

    async def test_records_which_structure_it_came_from(
        self, app, client, saved
    ) -> None:
        body = (
            await client.post(
                "/api/devsim/jobs",
                json={"structure_id": saved, "spec": spec_body()},
            )
        ).json()
        async with app.state.sessionmaker() as session:
            job = await session.get(Job, body["id"])
        assert json.loads(job.source)["structure"] == "contacts.str"

    async def test_the_client_cannot_forge_the_structure_name(
        self, app, client, saved
    ) -> None:
        body = (
            await client.post(
                "/api/devsim/jobs",
                json={
                    "structure_id": saved,
                    "spec": spec_body(structure="어딘가 다른 곳.str"),
                },
            )
        ).json()
        async with app.state.sessionmaker() as session:
            job = await session.get(Job, body["id"])
        assert json.loads(job.source)["structure"] == "contacts.str"

    async def test_rejects_an_electrode_that_is_not_there(
        self, client, saved
    ) -> None:
        spec = spec_body()
        spec["electrodes"][0]["interfaces"] = ["collector"]
        response = await client.post(
            "/api/devsim/jobs",
            json={"structure_id": saved, "spec": spec},
        )
        assert response.status_code == 422
        assert "collector" in response.json()["detail"]

    async def test_rejects_a_spec_with_two_sweeps(
        self, client, saved
    ) -> None:
        spec = spec_body()
        spec["biases"][2]["role"] = "sweep"
        spec["biases"][2]["sweep"] = {"start": 0.0, "stop": 1.0, "step": 0.5}
        response = await client.post(
            "/api/devsim/jobs",
            json={"structure_id": saved, "spec": spec},
        )
        assert response.status_code == 422

    async def test_rejects_too_many_bias_points(
        self, client, saved
    ) -> None:
        spec = spec_body()
        spec["biases"][3]["sweep"] = {"start": 0.0, "stop": 90.0, "points": 181}
        spec["biases"][2]["values"] = [float(v) for v in range(8)]
        response = await client.post(
            "/api/devsim/jobs",
            json={"structure_id": saved, "spec": spec},
        )
        assert response.status_code == 422

    async def test_an_unknown_structure_is_not_found(self, client, saved) -> None:
        response = await client.post(
            "/api/devsim/jobs",
            json={"structure_id": 99999, "spec": spec_body()},
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
        self, app, client
    ) -> None:
        async with app.state.sessionmaker() as session:
            job = Job(
                owner_id=await owner_id(app),
                status=JobStatus.SUCCEEDED,
                workdir="/tmp/none",
            )
            session.add(job)
            await session.commit()
            plain = job.id
        assert (await client.get(f"/api/devsim/runs/{plain}")).status_code == 404


class TestStructures:
    """보관해 둔 구조 목록.

    전극이 있는지 가려내는 일은 여기서 하지 않는다. 워커가 공정을 끝낼 때
    한 번만 하고 결과를 남긴다(`app/devsim/catalog.py`) — 목록을 열 때마다
    산출물을 전부 파싱하면 25단계 흐름 하나에 몇 초가 든다.
    """

    async def test_groups_structures_by_the_source_file(
        self, app, client, tmp_path, saved
    ) -> None:
        await clear_seeded(app)
        await store_structure(app, tmp_path, "other.in", "other.str")

        body = (await client.get("/api/devsim/structures")).json()
        assert sorted(one["source_path"] for one in body) == [
            "contacts.in",
            "other.in",
        ]
        # `.in` 하나에 구조 하나씩 붙어 있어야 한다.
        assert all(len(one["structures"]) == 1 for one in body)

    async def test_reports_what_the_picker_needs(self, app, client, saved) -> None:
        await clear_seeded(app)
        body = (await client.get("/api/devsim/structures")).json()
        entry = body[0]["structures"][0]
        assert entry["id"] == saved
        assert entry["filename"] == "contacts.str"
        assert entry["sequence"] == 1
        assert entry["size_bytes"] > 0

    async def test_several_structures_from_one_run_stay_together(
        self, app, client, tmp_path, saved
    ) -> None:
        await clear_seeded(app)
        await store_structure(app, tmp_path, "contacts.in", "later.str")
        body = (await client.get("/api/devsim/structures")).json()
        assert len(body) == 1
        assert sorted(one["filename"] for one in body[0]["structures"]) == [
            "contacts.str",
            "later.str",
        ]

    async def test_empty_when_nothing_is_kept(self, app, client) -> None:
        await clear_seeded(app)
        assert (await client.get("/api/devsim/structures")).json() == []

    async def test_a_new_user_starts_with_the_example(self, client) -> None:
        """가입 직후에도 소자 해석 탭에 볼 것이 있어야 한다.

        작업공간에는 `nmos.in` 이 들어가지만 소자 해석은 **실행 결과**를 받으므로,
        예제를 한 번 돌리기 전에는 그 탭이 비어 있었다.
        """
        body = (await client.get("/api/devsim/structures")).json()
        assert [one["source_path"] for one in body] == ["nmos.in"]
        assert body[0]["structures"][0]["filename"] == "nmos.str"

    async def test_the_example_can_be_analysed(self, client) -> None:
        body = (await client.get("/api/devsim/structures")).json()
        structure_id = body[0]["structures"][0]["id"]
        found = (
            await client.get(f"/api/devsim/structures/{structure_id}/interfaces")
        ).json()
        # nmos 최종 구조는 소스·게이트·드레인·뒷면이다.
        assert [one["key"] for one in found["interfaces"]] == [
            "source",
            "gate",
            "drain",
            "body",
        ]

    async def test_someone_elses_structures_are_not_listed(
        self, app, client, tmp_path, saved
    ) -> None:
        await clear_seeded(app)
        async with app.state.sessionmaker() as session:
            other = User(email="bob@example.com", password_hash="x", role="user")
            session.add(other)
            await session.flush()
            session.add(
                SavedStructure(
                    owner_id=other.id,
                    source_path="theirs.in",
                    job_id=None,
                    sequence=1,
                    filename="theirs.str",
                    path=str(tmp_path / "theirs.str"),
                    size_bytes=10,
                )
            )
            await session.commit()

        body = (await client.get("/api/devsim/structures")).json()
        assert [one["source_path"] for one in body] == ["contacts.in"]

    async def test_a_structure_outlives_its_job(
        self, app, client, tmp_path, saved
    ) -> None:
        """잡이 지워져도 구조는 남는다. 그것이 이 표의 존재 이유다."""
        async with app.state.sessionmaker() as session:
            row = await session.get(SavedStructure, saved)
            job = await session.get(Job, row.job_id)
            await session.delete(job)
            await session.commit()

        body = (await client.get("/api/devsim/structures")).json()
        assert body[0]["structures"][0]["job_id"] is None
        # 여전히 해석에 쓸 수 있어야 한다.
        assert (
            await client.get(f"/api/devsim/structures/{saved}/interfaces")
        ).status_code == 200


class TestSurface:
    """단면 그림도 보관본에서 그린다.

    플롯 쪽에도 같은 그림이 있지만 그쪽은 잡 산출물을 본다. 산출물은 스윕에
    지워지므로, 공정을 돌린 다음 날 전극을 짚으려면 여기서 나와야 한다.
    """

    async def test_draws_the_materials(self, client, saved) -> None:
        response = await client.get(f"/api/devsim/structures/{saved}/surface")
        assert response.status_code == 200
        body = response.json()
        assert body["x"] and body["y"] and body["triangles"]
        assert len(body["materials"]) == len(body["triangles"])
        assert "aluminum" in body["materials"]

    async def test_keeps_every_element(self, client, saved) -> None:
        # 물리량을 칠하면 그 해가 없는 요소가 빠진다. 재질 그림에서 층이 통째로
        # 사라지면 어디에 무엇이 붙었는지 볼 수 없다.
        body = (
            await client.get(f"/api/devsim/structures/{saved}/surface")
        ).json()
        assert body["values"] == []
        assert len(body["triangles"]) > 800

    async def test_someone_elses_structure_is_not_found(
        self, app, client, tmp_path
    ) -> None:
        async with app.state.sessionmaker() as session:
            other = User(email="carol@example.com", password_hash="x", role="user")
            session.add(other)
            await session.flush()
            row = SavedStructure(
                owner_id=other.id,
                source_path="theirs.in",
                job_id=None,
                sequence=1,
                filename="theirs.str",
                path=str(tmp_path / "theirs.str"),
                size_bytes=10,
            )
            session.add(row)
            await session.commit()
            stolen = row.id

        response = await client.get(f"/api/devsim/structures/{stolen}/surface")
        assert response.status_code == 404


class TestSavingRuns:
    """돌린 것을 전부 남기지 않는다.

    조건을 조금씩 바꿔 가며 여남은 번 돌리는 것이 보통인데, 그것이 다 목록에
    쌓이면 정작 비교하고 싶은 둘을 그 안에서 찾아야 한다. 남길 것은 사용자가
    이름을 붙여 고른다.
    """

    async def _finished(self, app, tmp_path, rows: int = 2) -> int:
        workdir = tmp_path / f"devjob-{rows}"
        workdir.mkdir()
        (workdir / "iv.json").write_text(
            json.dumps(
                {
                    "sweep": "Vd",
                    "biases": ["Vd", "Vg"],
                    "current_unit": "uA/um",
                    "rows": [
                        {
                            "sweep": i * 0.5,
                            "steps": {"Vg": 1.0},
                            "currents": {"Vd": 1.0, "Vg": 0.0},
                        }
                        for i in range(rows)
                    ],
                    "failures": [],
                    "total": rows,
                    "completed": rows,
                    "error": None,
                }
            )
        )
        async with app.state.sessionmaker() as session:
            job = Job(
                owner_id=await owner_id(app),
                kind=JobKind.DEVSIM,
                status=JobStatus.SUCCEEDED,
                workdir=str(workdir),
                source_path="mosfet/nmos.in",
                source=json.dumps(spec_body(structure="nmos.str")),
            )
            session.add(job)
            await session.commit()
            return job.id

    async def test_a_finished_run_is_not_saved_by_itself(
        self, app, client, tmp_path
    ) -> None:
        await self._finished(app, tmp_path)
        assert (await client.get("/api/devsim/runs")).json() == []

    async def test_the_curve_is_readable_without_saving(
        self, app, client, tmp_path
    ) -> None:
        # 방금 돌린 결과는 산출물에서 읽는다. 저장은 남길지 말지의 문제다.
        job_id = await self._finished(app, tmp_path)
        body = (await client.get(f"/api/devsim/jobs/{job_id}/result")).json()
        assert body["completed"] == 2
        assert body["current_unit"] == "uA/um"

    async def test_saving_gives_it_a_name(self, app, client, tmp_path) -> None:
        job_id = await self._finished(app, tmp_path)
        response = await client.post(
            "/api/devsim/runs", json={"job_id": job_id, "label": "두꺼운 산화막"}
        )
        assert response.status_code == 201
        assert response.json()["label"] == "두꺼운 산화막"

        listed = (await client.get("/api/devsim/runs")).json()
        assert [one["label"] for one in listed] == ["두꺼운 산화막"]

    async def test_saving_remembers_where_it_came_from(
        self, app, client, tmp_path
    ) -> None:
        # 구조 파일 이름만으로는 여러 흐름에서 같은 이름이 나올 수 있다.
        job_id = await self._finished(app, tmp_path)
        body = (
            await client.post(
                "/api/devsim/runs", json={"job_id": job_id, "label": "가"}
            )
        ).json()
        assert body["source_path"] == "mosfet/nmos.in"
        assert body["structure"] == "nmos.str"

    async def test_saving_twice_replaces_rather_than_piles_up(
        self, app, client, tmp_path
    ) -> None:
        job_id = await self._finished(app, tmp_path)
        await client.post("/api/devsim/runs", json={"job_id": job_id, "label": "가"})
        await client.post("/api/devsim/runs", json={"job_id": job_id, "label": "나"})
        listed = (await client.get("/api/devsim/runs")).json()
        assert [one["label"] for one in listed] == ["나"]

    async def test_renaming_a_saved_run(self, app, client, tmp_path) -> None:
        job_id = await self._finished(app, tmp_path)
        await client.post("/api/devsim/runs", json={"job_id": job_id, "label": "가"})
        response = await client.patch(
            f"/api/devsim/runs/{job_id}", json={"label": "얇은 산화막"}
        )
        assert response.status_code == 200
        assert response.json()["label"] == "얇은 산화막"

    async def test_renaming_something_never_saved_is_not_found(
        self, app, client, tmp_path
    ) -> None:
        job_id = await self._finished(app, tmp_path)
        response = await client.patch(
            f"/api/devsim/runs/{job_id}", json={"label": "가"}
        )
        assert response.status_code == 404

    async def test_forgetting_a_saved_run(self, app, client, tmp_path) -> None:
        job_id = await self._finished(app, tmp_path)
        await client.post("/api/devsim/runs", json={"job_id": job_id, "label": "가"})
        assert (
            await client.delete(f"/api/devsim/runs/{job_id}")
        ).status_code == 204
        assert (await client.get("/api/devsim/runs")).json() == []

    async def test_nothing_solved_cannot_be_saved(
        self, app, client, tmp_path
    ) -> None:
        job_id = await self._finished(app, tmp_path, rows=0)
        response = await client.post(
            "/api/devsim/runs", json={"job_id": job_id, "label": "가"}
        )
        assert response.status_code == 422

    async def test_someone_elses_job_cannot_be_saved(
        self, app, client, tmp_path
    ) -> None:
        async with app.state.sessionmaker() as session:
            other = User(email="dave@example.com", password_hash="x", role="user")
            session.add(other)
            await session.flush()
            job = Job(
                owner_id=other.id,
                kind=JobKind.DEVSIM,
                status=JobStatus.SUCCEEDED,
                workdir=str(tmp_path / "theirs"),
            )
            session.add(job)
            await session.commit()
            stolen = job.id

        response = await client.post(
            "/api/devsim/runs", json={"job_id": stolen, "label": "가"}
        )
        assert response.status_code == 404
