"""워커 루프.

큐에서 잡을 꺼내 샌드박스에서 돌리고 결과를 기록한다. 큐(queue.py)와 실행
(runner/)을 잇는 얇은 층이며, 실패해도 루프가 멈추지 않는 것이 핵심 책임이다.

시뮬레이션은 CPU 를 오래 붙잡는 동기 작업이라 이벤트 루프에서 직접 돌리면 안
된다. 스레드로 넘겨서 상태 조회 같은 다른 요청이 막히지 않게 한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    Artifact,
    DevSimResult,
    Job,
    JobKind,
    JobStatus,
    SavedStructure,
    SourceRevision,
)
from app.devsim.catalog import place_files
from app.devsim.service import DEFAULT_IMAGE as DEVSIM_IMAGE
from app.devsim.service import DEFAULT_LIMITS as DEVSIM_LIMITS
from app.devsim.service import DeviceResult, run_device_simulation
from app.jobs.queue import JobQueue
from app.runner.results import SimulationResult
from app.runner.runner import run_simulation
from app.runner.sandbox import SandboxLimits

logger = logging.getLogger(__name__)

#: 큐가 비었을 때 다음 확인까지 기다리는 시간. 이 규모에서는 폴링으로 충분하고,
#: 알림 채널을 추가하면 워커가 죽었을 때 복구 경로가 하나 더 늘어난다.
_IDLE_POLL_SECONDS = 2.0

#: 죽은 워커가 남긴 잡을 되돌리는 기준. 잡 타임아웃보다 넉넉히 길어야 한다.
#: 그렇지 않으면 정상 실행 중인 잡을 빼앗아 중복 실행하게 된다.
_STALE_MULTIPLIER = 3


class Worker:
    def __init__(
        self,
        queue: JobQueue,
        sessionmaker: async_sessionmaker[AsyncSession],
        jobs_root: Path,
        image: str,
        limits: SandboxLimits | None = None,
        devsim_image: str = DEVSIM_IMAGE,
        devsim_limits: SandboxLimits | None = None,
        structures_root: Path | None = None,
    ) -> None:
        self.queue = queue
        self.sessionmaker = sessionmaker
        self.jobs_root = jobs_root
        #: 전극이 있는 `.str` 을 오래 두는 곳. 잡 작업디렉토리 밖이라 스윕이
        #: 건드리지 않는다.
        self.structures_root = structures_root or Path("var/structures")
        self.image = image
        self.limits = limits or SandboxLimits()
        # 소자 해석은 상한이 다르다. 직접 솔버가 메모리를 더 쓰고 오래 돈다.
        self.devsim_image = devsim_image
        self.devsim_limits = devsim_limits or DEVSIM_LIMITS

    async def run_forever(self, stop: asyncio.Event) -> None:
        """중지 신호가 올 때까지 잡을 처리한다."""
        while not stop.is_set():
            processed = await self.run_once()
            if not processed:
                await self._sleep_or_stop(stop, _IDLE_POLL_SECONDS)

    async def run_once(self) -> bool:
        """잡 하나를 처리한다.

        Returns:
            처리한 잡이 있었으면 True.
        """
        job = await self.queue.claim_next()
        if job is None:
            return False

        try:
            result = await self._execute(job.id, job.workdir, job.kind)
        except Exception:
            # 한 잡의 실패로 워커가 멈추면 큐 전체가 정지한다. 잡만 실패로
            # 기록하고 루프는 계속 돈다.
            logger.exception("잡 %s 실행 중 예외", job.id)
            await self.queue.mark_finished(
                job.id,
                status=JobStatus.FAILED,
                log="워커에서 예기치 못한 오류가 발생했습니다.",
                exit_code=None,
            )
            return True

        await self._record(job.id, result)
        return True

    async def recover_stale(self) -> int:
        """죽은 워커가 남긴 잡을 큐로 되돌린다. 기동 시 한 번 부른다."""
        return await self.queue.requeue_stale(
            max_runtime=timedelta(
                seconds=self.limits.timeout_seconds * _STALE_MULTIPLIER
            )
        )

    async def _execute(
        self, job_id: int, workdir: str, kind: str
    ) -> SimulationResult | DeviceResult:
        """잡 종류에 따라 무엇을 돌릴지 고른다.

        여기가 두 종류가 갈리는 **유일한** 자리다. 큐·중단·타임아웃·로그·산출물·
        청소는 아래위로 전부 공유한다.
        """
        source = await self._load_source(job_id)
        # CPU 를 오래 쓰는 동기 호출이라 이벤트 루프 밖으로 내보낸다.
        if kind == JobKind.DEVSIM:
            return await asyncio.to_thread(
                run_device_simulation,
                source,
                Path(workdir),
                self.devsim_image,
                self.devsim_limits,
            )
        return await asyncio.to_thread(
            run_simulation,
            source,
            Path(workdir),
            self.image,
            self.limits,
        )

    async def _load_source(self, job_id: int) -> str:
        """돌릴 소스. **제출 시점의 스냅샷을 쓴다.**

        경로만 들고 파일을 다시 읽으면, 제출 뒤 사용자가 파일을 고쳤을 때
        결과와 입력이 어긋난다. 예전 프로젝트 모델로 만들어진 잡은 리비전에서
        읽는다.
        """
        async with self.sessionmaker() as session:
            from app.db.models import Job

            job = await session.get(Job, job_id)
            if job.source is not None:
                return job.source
            revision = await session.get(SourceRevision, job.source_revision_id)
            return revision.source

    async def _record(
        self, job_id: int, result: SimulationResult | DeviceResult
    ) -> None:
        if isinstance(result, DeviceResult):
            await self._save_artifacts(job_id, result.artifacts)
            await self._save_dataset(job_id, result)
        else:
            await self._save_artifacts(job_id, result.structure_files)
            if result.succeeded:
                await self._save_structures(job_id, result.structure_files)
        await self.queue.mark_finished(
            job_id,
            status=_status_for(result),
            log=result.log,
            exit_code=result.exit_code,
        )

    async def _save_artifacts(
        self, job_id: int, paths: Sequence[Path]
    ) -> None:
        if not paths:
            return
        async with self.sessionmaker() as session:
            for sequence, path in enumerate(paths, start=1):
                session.add(
                    Artifact(
                        job_id=job_id,
                        filename=path.name,
                        path=str(path),
                        size_bytes=path.stat().st_size,
                        sequence=sequence,
                    )
                )
            await session.commit()

    async def _save_structures(
        self, job_id: int, files: Sequence[Path]
    ) -> None:
        """전극이 있는 구조를 보관소로 옮긴다.

        같은 `.in` 을 다시 돌렸으면 그 `.in` 의 옛 보관본은 파일과 행 모두
        지우고 새로 채운다. 공정 코드를 고쳐 다시 돌렸는데 옛 구조가 목록에
        남아 있으면 어느 것이 지금 코드의 결과인지 구분할 수 없다.

        여기서 나는 오류로 잡을 실패시키지 않는다. 공정 결과 자체는 멀쩡하다.
        """
        async with self.sessionmaker() as session:
            job = await session.get(Job, job_id)
            if job is None or not job.source_path:
                return
            try:
                placed = await asyncio.to_thread(
                    place_files,
                    self.structures_root,
                    job.owner_id,
                    job.source_path,
                    list(enumerate(files, start=1)),
                )
            except OSError:
                logger.warning("구조 보관에 실패했습니다", exc_info=True)
                return

            await session.execute(
                delete(SavedStructure).where(
                    SavedStructure.owner_id == job.owner_id,
                    SavedStructure.source_path == job.source_path,
                )
            )
            for entry in placed:
                session.add(
                    SavedStructure(
                        owner_id=job.owner_id,
                        source_path=job.source_path,
                        job_id=job_id,
                        sequence=entry.sequence,
                        filename=entry.filename,
                        path=entry.path,
                        size_bytes=entry.size_bytes,
                    )
                )
            await session.commit()
            logger.info(
                "%s 에서 전극이 있는 구조 %d개를 보관했습니다",
                job.source_path,
                len(placed),
            )

    async def _save_dataset(self, job_id: int, result: DeviceResult) -> None:
        """곡선을 DB 에도 남긴다.

        산출물은 유휴·쿼터 스윕에 지워진다(`app/jobs/sweeper.py`). 비교 기능은
        예전 해석을 다시 불러와야 하므로 결과만은 표에 둔다 — 수백 행짜리라 작다.
        부분 결과라도 남긴다. 사용자가 볼 곡선이 있으면 비교할 값도 있다.
        """
        if not result.dataset or not result.dataset.get("completed"):
            return
        try:
            spec = json.loads(result.spec_json or "{}")
        except ValueError:
            spec = {}
        async with self.sessionmaker() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return
            session.add(
                DevSimResult(
                    job_id=job_id,
                    owner_id=job.owner_id,
                    label=str(spec.get("label") or "해석")[:120],
                    structure=str(spec.get("structure") or "")[:255],
                    spec=result.spec_json or "{}",
                    data=json.dumps(result.dataset),
                )
            )
            await session.commit()

    @staticmethod
    async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
        """중지 신호가 오면 즉시 깨어난다. 종료가 폴링 주기만큼 늦어지지 않는다."""
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            pass


def _status_for(result: SimulationResult | DeviceResult) -> JobStatus:
    """실행 결과를 잡 상태로 옮긴다.

    종료 코드로 판정하지 않는다. 시뮬레이터는 커맨드 오류가 있어도 exit 0 으로
    끝나므로, 종료 코드만 보면 실패한 잡이 성공으로 기록된다.
    """
    if result.timed_out:
        return JobStatus.TIMED_OUT
    return JobStatus.SUCCEEDED if result.succeeded else JobStatus.FAILED
