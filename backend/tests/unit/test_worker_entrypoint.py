"""워커 프로세스 진입점.

워커는 API 와 별도 프로세스로 돈다. 여기서 검증하는 것은 시뮬레이션 실행이
아니라(그건 test_worker.py 의 몫) **프로세스로서 제대로 살고 죽는가**다:
설정을 옳게 읽는지, 기동할 때 죽은 워커의 잔해를 치우는지, 종료 신호에 응답하는지.
"""

from __future__ import annotations

import asyncio
import signal
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import Base, Job, JobStatus, Project, SourceRevision, User
from app.jobs.main import build_worker, install_signal_handlers, run_loops, run_worker


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}",
        jobs_root=tmp_path / "jobs",
        sandbox_image="tcad/suprem:test",
        # 3배수(_STALE_MULTIPLIER)를 곱해도 짧게 유지해, 오래된 잡을 몇 초
        # 차이로 만들어낼 수 있게 한다.
        job_timeout_seconds=1,
        max_concurrent_jobs=3,
    )


@pytest.fixture
async def prepared_database(settings):
    """스키마와 잡 하나를 심어 둔 DB. 워커가 자기 엔진으로 다시 연다."""
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def insert_running_job(maker, started_at: datetime) -> int:
    async with maker() as session:
        user = User(email="w@example.com", password_hash="x")
        session.add(user)
        await session.flush()
        project = Project(owner_id=user.id, name="p")
        session.add(project)
        await session.flush()
        revision = SourceRevision(project_id=project.id, revision=1, source="x\n")
        session.add(revision)
        await session.flush()
        job = Job(
            owner_id=user.id,
            source_revision_id=revision.id,
            workdir="/tmp/nowhere",
            status=JobStatus.RUNNING,
            started_at=started_at,
        )
        session.add(job)
        await session.commit()
        return job.id


class TestBuildWorker:
    def test_reads_image_and_paths_from_settings(self, settings) -> None:
        worker = build_worker(settings, sessionmaker=None)

        assert worker.image == "tcad/suprem:test"
        assert worker.jobs_root == settings.jobs_root

    def test_job_timeout_comes_from_settings(self, settings) -> None:
        """설정과 샌드박스 제한이 어긋나면 타임아웃 값이 조용히 무시된다."""
        worker = build_worker(settings, sessionmaker=None)

        assert worker.limits.timeout_seconds == settings.job_timeout_seconds

    def test_queue_capacity_comes_from_settings(self, settings) -> None:
        worker = build_worker(settings, sessionmaker=None)

        assert worker.queue.max_concurrent == settings.max_concurrent_jobs


class TestRunWorker:
    async def test_stops_when_signalled(self, settings, prepared_database) -> None:
        """중지 신호를 미리 올려 두면 잡을 잡지 않고 곧바로 끝난다."""
        stop = asyncio.Event()
        stop.set()

        await asyncio.wait_for(run_worker(settings, stop), timeout=5)

    async def test_requeues_jobs_left_by_a_dead_worker(
        self, settings, prepared_database
    ) -> None:
        """워커가 죽으면 잡이 RUNNING 으로 남아 정원을 영구히 갉아먹는다."""
        stale_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        job_id = await insert_running_job(prepared_database, stale_at)

        stop = asyncio.Event()
        stop.set()
        await asyncio.wait_for(run_worker(settings, stop), timeout=5)

        async with prepared_database() as session:
            assert (await session.get(Job, job_id)).status is JobStatus.QUEUED

    async def test_leaves_recently_started_jobs_alone(
        self, settings, prepared_database
    ) -> None:
        """돌고 있는 잡을 되돌리면 같은 시뮬레이션이 두 번 실행된다."""
        job_id = await insert_running_job(
            prepared_database, datetime.now(timezone.utc)
        )

        stop = asyncio.Event()
        stop.set()
        await asyncio.wait_for(run_worker(settings, stop), timeout=5)

        async with prepared_database() as session:
            assert (await session.get(Job, job_id)).status is JobStatus.RUNNING


class TestRunLoops:
    async def test_runs_one_loop_per_configured_slot(self) -> None:
        """루프가 하나뿐이면 동시 실행 상한이 몇이든 잡은 한 번에 하나씩 돈다."""
        started = 0

        class SpyWorker:
            async def run_forever(self, stop: asyncio.Event) -> None:
                nonlocal started
                started += 1
                await stop.wait()

        stop = asyncio.Event()
        task = asyncio.create_task(run_loops(SpyWorker(), stop, concurrency=3))
        while started < 3:
            await asyncio.sleep(0)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

        assert started == 3

    async def test_all_loops_exit_on_stop(self) -> None:
        finished = 0

        class SpyWorker:
            async def run_forever(self, stop: asyncio.Event) -> None:
                nonlocal finished
                await stop.wait()
                finished += 1

        stop = asyncio.Event()
        task = asyncio.create_task(run_loops(SpyWorker(), stop, concurrency=4))
        await asyncio.sleep(0)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

        assert finished == 4


class TestSignalHandlers:
    """실제 시그널을 쏘지 않는다. 핸들러 등록이 잘못돼 있으면 시그널이 그대로
    프로세스를 죽여서 테스트 러너까지 함께 내려간다."""

    class FakeLoop:
        def __init__(self) -> None:
            self.handlers: dict[signal.Signals, object] = {}

        def add_signal_handler(self, sig, callback) -> None:
            self.handlers[sig] = callback

    def test_handles_sigterm_and_sigint(self) -> None:
        """SIGTERM 은 systemd 가, SIGINT 는 터미널이 보낸다. 둘 다 필요하다."""
        loop = self.FakeLoop()

        install_signal_handlers(loop, asyncio.Event())

        assert set(loop.handlers) == {signal.SIGTERM, signal.SIGINT}

    @pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
    def test_handler_requests_shutdown(self, sig) -> None:
        loop = self.FakeLoop()
        stop = asyncio.Event()

        install_signal_handlers(loop, stop)
        loop.handlers[sig]()

        assert stop.is_set()

    def test_survives_platforms_without_signal_support(self) -> None:
        """add_signal_handler 가 없는 환경에서도 워커는 떠야 한다."""

        class UnsupportedLoop:
            def add_signal_handler(self, sig, callback):
                raise NotImplementedError

        install_signal_handlers(UnsupportedLoop(), asyncio.Event())
