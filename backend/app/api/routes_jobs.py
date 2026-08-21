"""잡 제출과 조회 엔드포인트."""

from __future__ import annotations

from datetime import UTC, datetime

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.throttle import throttle_submit
from app.api.deps import (
    current_session,
    get_app_settings,
    get_db,
    get_queue,
    owned_artifact,
    owned_job,
)
from app.auth.models import Session
from app.core.config import Settings
from app.db.models import Artifact, Job, JobKind, JobStatus
from app.devsim.progress import scan_devsim_progress
from app.devsim.spec import DeviceSpec, total_points
from app.jobs.progress import scan_progress
from app.jobs.queue import JobQueue
from app.runner.control import kill_container
from app.runner.logfile import read_full_log
from app.runner.runner import was_truncated
from app.runner.sandbox import container_name
from app.projects.service import (
    ProjectNotFound,
    get_owned_project,
    latest_revision,
)

router = APIRouter(tags=["jobs"])


class JobResponse(BaseModel):
    id: int
    status: str
    #: 무엇을 돌린 잡인가 — `suprem` 공정 실행, `devsim` 소자 해석. 화면이
    #: 어떤 결과 보기를 띄울지 이걸로 고른다.
    kind: str = JobKind.SUPREM
    #: 예전 프로젝트 모델의 잔재. 파일로 돌린 잡은 비어 있다 — 필수로 두면
    #: 조회가 직렬화 단계에서 터지고 화면은 폴링 실패만 반복한다.
    source_revision_id: int | None = None
    #: 어느 파일을 돌렸는지. 리비전 기반 잡은 비어 있다.
    source_path: str | None = None


class JobDetailResponse(JobResponse):
    #: **로그는 여기 싣지 않는다.** 이 응답은 잡이 도는 동안 1.5 초마다 다시
    #: 받는다. 로그를 실으면 매번 실행 출력 전체가 따라오고, 실측으로 한 번에
    #: 97 KB 였다 — 앞에 선 nginx 의 프록시 버퍼(기본 약 36 KB)를 넘겨 디스크로
    #: 흘려보내게 만드는 크기다. 그 쓰기가 막히자 응답이 깨져 완료를 영영
    #: 감지하지 못하고 같은 요청을 무한히 반복했다. 로그는 `/console` 로 따로,
    #: 끝난 뒤 한 번만 받는다.
    exit_code: int | None
    #: 제출 시각. 화면은 잡 번호 대신 이걸로 실행을 가리킨다 — 번호는 전체
    #: 사용자가 공유하는 기본키라 혼자 두 번 돌려도 건너뛴다.
    created_at: datetime
    #: 실행에 걸린 시간(초). 도는 중이면 지금까지, 끝났으면 총 실행 시간이다.
    #: 아직 큐에서 기다리는 중이면 None — 대기 시간은 실행 시간이 아니다.
    #:
    #: **서버가 계산해서 내려준다.** 브라우저가 제출 시각과 자기 시계를 빼서
    #: 구하면 시계가 어긋난 만큼 그대로 틀린다. 화면은 이 값에서 이어 세기만
    #: 하면 되고, 다음 조회가 다시 맞춰 준다.
    elapsed_seconds: float | None = None
    #: 도는 동안의 공정 진행. 끝난 잡에는 없다 — 그때는 산출물 목록이 곧
    #: 결과이고, 진행 문구가 남으면 지워지지 않는 안내가 된다.
    progress: "JobProgressResponse | None" = None
    artifacts: list["ArtifactResponse"]


class JobProgressResponse(BaseModel):
    """소스가 적어 둔 `structure out=` 중 몇 개가 저장됐는지."""

    done: int
    total: int
    #: 마지막으로 저장된 구조 파일 이름. 아직 하나도 없으면 None.
    latest: str | None


class ArtifactResponse(BaseModel):
    sequence: int
    filename: str
    size_bytes: int


def _aware(moment: datetime) -> datetime:
    """시간대를 반드시 붙여서 내보낸다.

    Postgres 는 timestamptz 라 시간대를 갖고 오지만 SQLite 는 그렇지 않다.
    시간대 없는 값을 그대로 보내면 브라우저가 **현지 시각으로 읽어** 몇 시간
    어긋난 시각을 보여준다.
    """
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _elapsed_seconds(job: Job) -> float | None:
    """실행에 걸린 시간. 아직 시작하지 않았으면 None.

    끝난 잡은 `finished_at` 에서 멈춘다. 지금 시각을 쓰면 이미 끝난 실행의
    "총 실행 시간"이 화면을 열어 둔 동안 계속 늘어난다.
    """
    if job.started_at is None:
        return None
    end = _aware(job.finished_at) if job.finished_at else datetime.now(UTC)
    # 워커와 API 의 시계가 조금 어긋나면 음수가 나올 수 있다. 음수 시간을
    # 그대로 내보내면 화면이 "-3s" 를 센다.
    return max(0.0, (end - _aware(job.started_at)).total_seconds())


def _devsim_total(source: str) -> int:
    """해석 조건에서 풀어야 할 바이어스 점 수. 진행률의 분모다."""
    try:
        return total_points(DeviceSpec.model_validate_json(source))
    except ValueError:
        # 조건이 깨졌으면 워커가 실패로 기록한다. 여기서는 조용히 진행률만 접는다.
        return 0


def _progress(job: Job) -> JobProgressResponse | None:
    """도는 동안의 진행. 끝났거나 셀 근거가 없으면 None.

    세는 방법이 잡 종류마다 다르다. 공정 실행은 `.str` 파일 개수를, 소자 해석은
    해석기가 흘려보내는 `iv.jsonl` 의 줄 수를 센다. 로그를 못 쓰는 사정은 같다 —
    stdout 은 파이프로 받아 끝날 때 한꺼번에 저장한다.
    """
    if job.status is not JobStatus.RUNNING or not job.source or not job.workdir:
        return None
    if job.kind == JobKind.DEVSIM:
        found = scan_devsim_progress(Path(job.workdir), _devsim_total(job.source))
    else:
        found = scan_progress(Path(job.workdir), job.source)
    if found is None:
        return None
    return JobProgressResponse(
        done=found.done, total=found.total, latest=found.latest
    )


@router.post(
    "/projects/{project_id}/jobs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(throttle_submit)],
)
async def submit(
    project_id: int,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
    queue: JobQueue = Depends(get_queue),
    settings: Settings = Depends(get_app_settings),
) -> JobResponse:
    """프로젝트의 최신 리비전으로 시뮬레이션을 제출한다."""
    owner_id = int(session.user_id)
    try:
        project = await get_owned_project(db, project_id, owner_id)
    except ProjectNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로젝트를 찾을 수 없습니다",
        ) from None

    revision = await latest_revision(db, project)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="저장된 소스가 없습니다. 먼저 코드를 저장해 주세요.",
        )

    # 경로는 서버가 정한다. 사용자 입력이 섞이면 경로 탈출로 이어진다.
    #
    # 잡 id 대신 UUID 를 쓴다. id 를 쓰려면 삽입 후에 경로를 채워 넣어야 하는데,
    # 그 사이에 워커가 잡을 집어가면 빈 경로로 실행된다. UUID 는 삽입 전에
    # 정할 수 있어 그 경합이 아예 없고, 순차 id 가 경로로 새지도 않는다.
    workdir = Path(settings.jobs_root).resolve() / f"job-{uuid4().hex}"

    job = await queue.enqueue(
        owner_id=owner_id,
        source_revision_id=revision.id,
        workdir=str(workdir),
    )

    return JobResponse(
        id=job.id,
        status=job.status.value,
        source_revision_id=revision.id,
    )


@router.get("/jobs/{job_id}")
async def detail(
    job: Job = Depends(owned_job),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    artifacts = (
        await db.execute(
            select(Artifact)
            .where(Artifact.job_id == job.id)
            .order_by(Artifact.sequence)
        )
    ).scalars().all()

    return JobDetailResponse(
        id=job.id,
        status=job.status.value,
        source_revision_id=job.source_revision_id,
        source_path=job.source_path,
        created_at=_aware(job.created_at),
        elapsed_seconds=_elapsed_seconds(job),
        progress=_progress(job),
        exit_code=job.exit_code,
        artifacts=[
            ArtifactResponse(
                sequence=a.sequence, filename=a.filename, size_bytes=a.size_bytes
            )
            for a in artifacts
        ],
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel(
    job: Job = Depends(owned_job),
    queue: JobQueue = Depends(get_queue),
) -> JobResponse:
    """실행 중이거나 대기 중인 잡을 멈춘다.

    컨테이너 이름은 workdir 에서 결정론적으로 나오므로, 워커에게 신호를 보내는
    통로 없이 여기서 바로 죽일 수 있다.

    **상태를 먼저 바꾸고 컨테이너를 죽인다.** 순서가 반대면, 컨테이너가 죽은 것을
    워커가 먼저 읽어 "실패"로 기록해 버린다. 상태가 이미 CANCELLED 면 워커의
    기록은 무시된다(JobQueue.mark_finished 의 RUNNING 가드).
    """
    before = await queue.cancel(job.id)
    if before is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 끝난 잡입니다",
        )

    if before.status is JobStatus.RUNNING:
        # 죽이지 못해도 중단은 성립한다. 컨테이너는 타임아웃이 거둬 가고,
        # 사용자에게는 이미 멈춘 것으로 보인다.
        kill_container(container_name(Path(before.workdir)))

    return JobResponse(
        id=job.id,
        status=JobStatus.CANCELLED.value,
        source_revision_id=job.source_revision_id,
    )


class ConsoleResponse(BaseModel):
    """화면에 뿌릴 실행 출력."""

    #: DB 에 보관한 미리보기. 작업디렉토리가 청소돼도 남는다.
    log: str | None
    #: 위 log 가 상한에 걸려 잘렸는지. 참이면 화면이 전문 내려받기를 안내한다.
    #: 잘렸다는 말 없이 보여 주면 사용자는 로그가 그게 전부인 줄 알고 없는
    #: 원인을 찾는다.
    truncated: bool = False


@router.get("/jobs/{job_id}/console", response_model=ConsoleResponse)
async def console(job: Job = Depends(owned_job)) -> ConsoleResponse:
    """실행 출력. 상태 조회와 나눠 둔 이유는 `JobDetailResponse` 주석 참조.

    로그는 잡이 끝날 때 한 번 기록되므로(`app/jobs/queue.py finish`), 도는
    동안 여기를 되풀이해 부를 이유가 없다. 화면은 끝난 뒤 한 번만 받는다.
    """
    return ConsoleResponse(log=job.log, truncated=was_truncated(job.log))


@router.get("/jobs/{job_id}/log", response_class=PlainTextResponse)
async def full_log(job: Job = Depends(owned_job)) -> PlainTextResponse:
    """실행 로그 전문.

    화면에 뿌리는 `log` 는 DB 한 행이 무한정 커지지 않도록 상한을 두고 자른다.
    잘린 부분은 여기서 되찾는다.

    전문은 잡 작업디렉토리에 있으므로 산출물과 수명이 같다. 세션이 만료돼
    청소가 돌면 함께 사라지고, 그때는 잘린 미리보기만 남는다.
    """
    log = read_full_log(Path(job.workdir)) if job.workdir else None
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="로그 전문이 정리되어 더 이상 남아 있지 않습니다",
        )
    # text/plain 으로 내려야 브라우저가 실행하지 않는다. 로그에는 사용자가 쓴
    # 코드가 그대로 들어 있어 HTML 로 해석되면 그대로 저장형 XSS 가 된다.
    return PlainTextResponse(
        log,
        headers={
            "Content-Disposition": f'attachment; filename="job-{job.id}.log"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/jobs/{job_id}/artifacts/{sequence}")
async def artifact_content(
    artifact: Artifact = Depends(owned_artifact),
) -> dict[str, str]:
    """`.str` 파일 원문. 그림용 변환은 routes_plot 이 한다."""
    path = Path(artifact.path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="산출물이 정리되어 더 이상 남아 있지 않습니다",
        )
    return {"filename": artifact.filename, "content": path.read_text()}


@router.get("/projects/{project_id}/jobs")
async def index(
    project_id: int,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> list[JobResponse]:
    owner_id = int(session.user_id)
    try:
        await get_owned_project(db, project_id, owner_id)
    except ProjectNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로젝트를 찾을 수 없습니다",
        ) from None

    from app.db.models import SourceRevision

    # INNER JOIN 이라 리비전이 없는 잡(파일 기반)은 애초에 걸리지 않는다.
    # 프로젝트별 목록은 예전 모델 전용이므로 그대로 둔다.
    jobs = (
        await db.execute(
            select(Job)
            .join(SourceRevision, Job.source_revision_id == SourceRevision.id)
            .where(SourceRevision.project_id == project_id)
            .order_by(Job.created_at.desc(), Job.id.desc())
        )
    ).scalars().all()

    return [
        JobResponse(
            id=j.id,
            status=j.status.value,
            source_revision_id=j.source_revision_id,
            source_path=j.source_path,
        )
        for j in jobs
    ]



JobDetailResponse.model_rebuild()
