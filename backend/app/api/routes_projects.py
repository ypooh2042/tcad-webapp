"""프로젝트와 소스 리비전 엔드포인트."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_session, get_db
from app.auth.models import Session
from app.projects.service import (
    DuplicateProjectName,
    ProjectNotFound,
    add_revision,
    create_project,
    get_owned_project,
    list_projects,
)

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
