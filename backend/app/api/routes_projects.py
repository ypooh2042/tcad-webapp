"""프로젝트와 소스 리비전 엔드포인트."""

from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_session, get_db
from app.auth.models import Session
from app.projects.service import (
    DuplicateProjectName,
    ProjectBusy,
    ProjectNotFound,
    add_revision,
    create_project,
    delete_project,
    get_owned_project,
    latest_revision,
    list_projects,
    rename_project,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])

#: 소스 길이 상한. 예제 중 가장 긴 CMOS.in 이 약 3KB 라 넉넉하다. 상한이 없으면
#: 한 번의 요청으로 DB 를 채울 수 있다.
_MAX_SOURCE_CHARS = 200_000


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectResponse(BaseModel):
    id: int
    name: str


class RevisionCreate(BaseModel):
    source: str = Field(max_length=_MAX_SOURCE_CHARS)


class RevisionResponse(BaseModel):
    id: int
    revision: int


class RevisionWithSource(RevisionResponse):
    source: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(
    payload: ProjectCreate,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    try:
        project = await create_project(db, int(session.user_id), payload.name)
    except DuplicateProjectName:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="같은 이름의 프로젝트가 이미 있습니다",
        ) from None
    return ProjectResponse(id=project.id, name=project.name)


@router.get("")
async def index(
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectResponse]:
    projects = await list_projects(db, int(session.user_id))
    return [ProjectResponse(id=p.id, name=p.name) for p in projects]


@router.patch("/{project_id}")
async def rename(
    project_id: int,
    payload: ProjectCreate,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """프로젝트 이름을 바꾼다. 소스와 잡은 그대로 둔다."""
    try:
        project = await rename_project(
            db, project_id, int(session.user_id), payload.name
        )
    except ProjectNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로젝트를 찾을 수 없습니다",
        ) from None
    except DuplicateProjectName:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="같은 이름의 프로젝트가 이미 있습니다",
        ) from None
    return ProjectResponse(id=project.id, name=project.name)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(
    project_id: int,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """프로젝트를 지운다. 소스·잡·산출물이 함께 사라지며 되돌릴 수 없다."""
    try:
        workdirs = await delete_project(db, project_id, int(session.user_id))
    except ProjectNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로젝트를 찾을 수 없습니다",
        ) from None
    except ProjectBusy:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="실행 중인 시뮬레이션이 있습니다. 끝난 뒤에 지워 주세요",
        ) from None

    # DB 는 행만 지운다. 디스크의 산출물은 여기서 치우지 않으면 영영 남는다.
    # 실패해도 삭제 자체는 이미 끝났으므로 요청을 실패시키지 않는다 — 남은
    # 디렉토리는 사용자가 할 수 있는 일이 없고, 지워진 프로젝트가 목록에
    # 되살아나는 편이 더 혼란스럽다.
    for workdir in workdirs:
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except OSError:
            logger.warning("작업 디렉토리를 지우지 못했습니다: %s", workdir)


@router.post("/{project_id}/revisions", status_code=status.HTTP_201_CREATED)
async def create_revision(
    project_id: int,
    payload: RevisionCreate,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> RevisionResponse:
    project = await _owned_or_404(db, project_id, session)
    revision = await add_revision(db, project, payload.source)
    return RevisionResponse(id=revision.id, revision=revision.revision)


@router.get("/{project_id}/revisions/latest")
async def latest(
    project_id: int,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> RevisionWithSource:
    """마지막으로 저장한 소스.

    프로젝트를 열 때 편집기를 채우는 데 쓴다. 이게 없으면 탭을 눌러도 이전
    프로젝트의 내용이 그대로 남아, 사용자가 엉뚱한 소스를 고치게 된다.
    """
    project = await _owned_or_404(db, project_id, session)
    revision = await latest_revision(db, project)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="저장된 소스가 없습니다",
        )
    return RevisionWithSource(
        id=revision.id, revision=revision.revision, source=revision.source
    )


async def _owned_or_404(db: AsyncSession, project_id: int, session: Session):
    """소유 확인. 없는 것과 남의 것을 같은 404 로 처리한다.

    구분해서 알리면 id 를 훑어 다른 사용자의 프로젝트 존재 여부를 알아낼 수 있다.
    """
    try:
        return await get_owned_project(db, project_id, int(session.user_id))
    except ProjectNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로젝트를 찾을 수 없습니다",
        ) from None
