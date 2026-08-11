"""워커 통합 테스트.

큐와 샌드박스를 잇는 층을 검증한다. 실제 컨테이너를 띄우는 테스트와, 실행을
가짜로 바꿔 워커 로직만 보는 테스트를 나눠 둔다. 후자는 Podman 없이도 돈다.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Artifact, Base, Job, JobStatus, Project, SourceRevision, User
from app.jobs.queue import JobQueue
from app.jobs.worker import Worker
from app.runner.results import SimulationResult
from app.runner.runner import DEFAULT_IMAGE
from app.runner.sandbox import SandboxLimits

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _sandbox_available() -> bool:
    if shutil.which("podman") is None:
        return False
    return (
        subprocess.run(
            ["podman", "image", "exists", DEFAULT_IMAGE], check=False
        ).returncode
        == 0
    )


requires_sandbox = pytest.mark.skipif(
    not _sandbox_available(), reason="podman 또는 샌드박스 이미지가 없습니다"
)


@pytest.fixture
async def sessionmaker_fixture():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def seed(sessionmaker_fixture):
    """사용자 + 프로젝트 + 리비전을 만들고 리비전 id 를 돌려준다."""

    async def _seed(source: str) -> tuple[int, int]:
        async with sessionmaker_fixture() as session:
            user = User(email="a@example.com", password_hash="x", role="user")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name=f"p{id(source)}")
            session.add(project)
            await session.flush()
            revision = SourceRevision(
                project_id=project.id, revision=1, source=source
            )
            session.add(revision)
            await session.commit()
            return user.id, revision.id

    return _seed


def make_worker(sessionmaker, tmp_path, limits=None) -> tuple[JobQueue, Worker]:
    queue = JobQueue(sessionmaker, max_concurrent=4)
    worker = Worker(
        queue=queue,
        sessionmaker=sessionmaker,
        jobs_root=tmp_path,
        image=DEFAULT_IMAGE,
        limits=limits or SandboxLimits(timeout_seconds=120),
    )
    return queue, worker


class TestWorkerLogic:
    """실행을 가짜로 바꿔 워커 자체의 동작만 본다."""

    async def test_returns_false_when_queue_empty(
        self, sessionmaker_fixture, tmp_path
    ) -> None:
        _, worker = make_worker(sessionmaker_fixture, tmp_path)
        assert await worker.run_once() is False

    async def test_failed_simulation_is_recorded_as_failed(
        self, sessionmaker_fixture, tmp_path, seed, monkeypatch
    ) -> None:
        """오류가 있어도 종료 코드는 0 이다. 상태는 로그 분석으로 정해야 한다."""
        owner_id, revision_id = await seed("quit\n")
        queue, worker = make_worker(sessionmaker_fixture, tmp_path)
        job = await queue.enqueue(owner_id, revision_id, str(tmp_path / "j"))

        def fake_run(*_args, **_kwargs):
            return SimulationResult(
                exit_code=0,
                log="errors detected on command input",
                timed_out=False,
                structure_files=(),
                errors=("errors detected on command input",),
            )

        monkeypatch.setattr("app.jobs.worker.run_simulation", fake_run)
        await worker.run_once()

        async with sessionmaker_fixture() as session:
            stored = await session.get(Job, job.id)
        assert stored.status is JobStatus.FAILED
        assert stored.exit_code == 0

    async def test_timeout_is_recorded_distinctly(
        self, sessionmaker_fixture, tmp_path, seed, monkeypatch
    ) -> None:
        owner_id, revision_id = await seed("quit\n")
        queue, worker = make_worker(sessionmaker_fixture, tmp_path)
        job = await queue.enqueue(owner_id, revision_id, str(tmp_path / "j"))

        monkeypatch.setattr(
            "app.jobs.worker.run_simulation",
            lambda *_a, **_k: SimulationResult(
                exit_code=-1,
                log="",
                timed_out=True,
                structure_files=(),
                errors=(),
            ),
        )
        await worker.run_once()

        async with sessionmaker_fixture() as session:
            stored = await session.get(Job, job.id)
        assert stored.status is JobStatus.TIMED_OUT

    async def test_crash_marks_job_failed_and_keeps_loop_alive(
        self, sessionmaker_fixture, tmp_path, seed, monkeypatch
    ) -> None:
        """한 잡의 예외로 워커가 멈추면 큐 전체가 정지한다."""
        owner_id, revision_id = await seed("quit\n")
        queue, worker = make_worker(sessionmaker_fixture, tmp_path)
        job = await queue.enqueue(owner_id, revision_id, str(tmp_path / "j"))

        def explode(*_args, **_kwargs):
            raise RuntimeError("컨테이너 런타임 장애")

        monkeypatch.setattr("app.jobs.worker.run_simulation", explode)
        assert await worker.run_once() is True

        async with sessionmaker_fixture() as session:
            stored = await session.get(Job, job.id)
        assert stored.status is JobStatus.FAILED
        assert stored.finished_at is not None

    async def test_stop_event_wakes_idle_worker_immediately(
        self, sessionmaker_fixture, tmp_path
    ) -> None:
        """종료가 폴링 주기만큼 늦어지면 배포가 느려진다."""
        _, worker = make_worker(sessionmaker_fixture, tmp_path)
        stop = asyncio.Event()

        async def stop_soon():
            await asyncio.sleep(0.05)
            stop.set()

        await asyncio.wait_for(
            asyncio.gather(worker.run_forever(stop), stop_soon()), timeout=2.0
        )


@requires_sandbox
class TestEndToEnd:
    """실제 컨테이너로 제출부터 산출물 기록까지 확인한다."""

    async def test_successful_run_records_artifacts(
        self, sessionmaker_fixture, tmp_path, seed
    ) -> None:
        source = (FIXTURES / "1d_multi_dopant.in").read_text()
        owner_id, revision_id = await seed(source)
        queue, worker = make_worker(sessionmaker_fixture, tmp_path)
        job = await queue.enqueue(owner_id, revision_id, str(tmp_path / "job1"))

        await worker.run_once()

        async with sessionmaker_fixture() as session:
            stored = await session.get(Job, job.id)
            artifacts = (
                await session.execute(
                    select(Artifact).where(Artifact.job_id == job.id)
                )
            ).scalars().all()

        assert stored.status is JobStatus.SUCCEEDED
        assert [a.filename for a in artifacts] == ["multi.str"]
        assert artifacts[0].size_bytes > 0
        assert Path(artifacts[0].path).exists()

    async def test_artifacts_are_numbered_in_creation_order(
        self, sessionmaker_fixture, tmp_path, seed
    ) -> None:
        """공정 단계 순서여야 한다. 이름순이면 흐름이 뒤섞인다."""
        source = (
            "option quiet\nmode one.dim\n"
            "line x loc=0 spacing=0.1 tag=top\n"
            "line x loc=1 spacing=0.1 tag=bot\n"
            "region silicon xlo=top xhi=bot\n"
            "bound exposed xlo=top xhi=top\n"
            "init boron conc=1e15\n"
            "structure out=zzz_first.str\n"
            "deposit oxide thick=0.05\n"
            "structure out=aaa_second.str\n"
        )
        owner_id, revision_id = await seed(source)
        queue, worker = make_worker(sessionmaker_fixture, tmp_path)
        job = await queue.enqueue(owner_id, revision_id, str(tmp_path / "job2"))

        await worker.run_once()

        async with sessionmaker_fixture() as session:
            artifacts = (
                await session.execute(
                    select(Artifact)
                    .where(Artifact.job_id == job.id)
                    .order_by(Artifact.sequence)
                )
            ).scalars().all()

        assert [a.filename for a in artifacts] == [
            "zzz_first.str",
            "aaa_second.str",
        ]

    async def test_shell_fallthrough_job_is_contained(
        self, sessionmaker_fixture, tmp_path, seed
    ) -> None:
        """적대적 소스를 큐로 제출해도 격리가 유지되는지 확인한다."""
        owner_id, revision_id = await seed("cat /etc/shadow\nquit\n")
        queue, worker = make_worker(sessionmaker_fixture, tmp_path)
        job = await queue.enqueue(owner_id, revision_id, str(tmp_path / "job3"))

        await worker.run_once()

        async with sessionmaker_fixture() as session:
            stored = await session.get(Job, job.id)
        assert "Permission denied" in stored.log
        assert "root:" not in stored.log
