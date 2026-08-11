"""잡 제출과 조회 엔드포인트."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_session, get_app_settings, get_db, get_queue
from app.auth.models import Session
from app.core.config import Settings
from app.db.models import Artifact, Job, JobStatus
from app.jobs.queue import JobQueue
from app.projects.service import (
    ProjectNotFound,
    get_owned_project,
    latest_revision,
)

router = APIRouter(tags=["jobs"])


class JobResponse(BaseModel):
    id: int
    status: str
    source_revision_id: int


class JobDetailResponse(JobResponse):
    log: str | None
    exit_code: int | None
    artifacts: list["ArtifactResponse"]


class ArtifactResponse(BaseModel):
    sequence: int
    filename: str
    size_bytes: int


@router.post("/projects/{project_id}/jobs", status_code=status.HTTP_201_CREATED)
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
    job_id: int,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    job = await _owned_job_or_404(db, job_id, session)
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
        log=job.log,
        exit_code=job.exit_code,
        artifacts=[
            ArtifactResponse(
                sequence=a.sequence, filename=a.filename, size_bytes=a.size_bytes
            )
            for a in artifacts
        ],
    )


@router.get("/jobs/{job_id}/artifacts/{sequence}")
async def artifact_content(
    job_id: int,
    sequence: int,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """`.str` 파일 원문. 파싱은 별도 엔드포인트에서 한다."""
    job = await _owned_job_or_404(db, job_id, session)
    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.job_id == job.id, Artifact.sequence == sequence
        )
    )
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="산출물을 찾을 수 없습니다"
        )

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
            id=j.id, status=j.status.value, source_revision_id=j.source_revision_id
        )
        for j in jobs
    ]


async def _owned_job_or_404(
    db: AsyncSession, job_id: int, session: Session
) -> Job:
    """소유 확인. 남의 잡은 "없음"과 같은 404 로 응답한다.

    잡 로그에는 사용자가 쓴 코드와 실행 결과가 그대로 들어 있다. 남의 것을
    읽히면 안 되고, 존재 여부조차 알려주면 안 된다.
    """
    job = await db.get(Job, job_id)
    if job is None or job.owner_id != int(session.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="잡을 찾을 수 없습니다"
        )
    return job


JobDetailResponse.model_rebuild()
