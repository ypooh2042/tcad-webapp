"""작업공간 파일 엔드포인트.

사용자에게는 자기 루트가 파일시스템 전부다. **서버의 절대경로는 응답에도 오류
메시지에도 절대 나가지 않는다** — 나가면 서버 구조를 알려주는 셈이다.

경로 안전은 app/workspace/paths.py 가 책임진다. 여기서는 예외를 HTTP 상태로
옮기는 일만 한다.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import current_session, get_app_settings, get_queue
from app.jobs.queue import JobQueue
from app.auth.models import Role, Session
from app.core.config import Settings
from app.workspace.factory import workspace_for
from app.workspace.paths import InvalidPath
from app.workspace.service import (
    QuotaExceeded,
    Workspace,
    WorkspaceConflict,
    WorkspaceNotFound,
)

router = APIRouter(prefix="/files", tags=["files"])

#: 소스 길이 상한. 예제 중 가장 긴 CMOS.in 이 약 3KB 라 넉넉하다.
_MAX_SOURCE_CHARS = 200_000

#: 경로 길이 상한. 이보다 길면 어차피 파일시스템이 받지 않는다.
_MAX_PATH_CHARS = 1024


class EntryResponse(BaseModel):
    path: str
    name: str
    is_dir: bool
    size_bytes: int


class TreeResponse(BaseModel):
    entries: list[EntryResponse]


class ContentResponse(BaseModel):
    path: str
    content: str


class WriteRequest(BaseModel):
    path: str = Field(min_length=1, max_length=_MAX_PATH_CHARS)
    content: str = Field(max_length=_MAX_SOURCE_CHARS)


class FolderRequest(BaseModel):
    path: str = Field(min_length=1, max_length=_MAX_PATH_CHARS)


class RenameRequest(BaseModel):
    path: str = Field(min_length=1, max_length=_MAX_PATH_CHARS)
    destination: str = Field(min_length=1, max_length=_MAX_PATH_CHARS)


class RunRequest(BaseModel):
    path: str = Field(min_length=1, max_length=_MAX_PATH_CHARS)


class RunResponse(BaseModel):
    id: int
    status: str
    source_path: str


class UsageResponse(BaseModel):
    used_bytes: int
    quota_bytes: int
    remaining_bytes: int


def current_workspace(
    session: Session = Depends(current_session),
    settings: Settings = Depends(get_app_settings),
) -> Workspace:
    return workspace_for(
        settings,
        user_id=int(session.user_id),
        is_admin=session.role is Role.ADMIN,
    )


def _handle(error: Exception) -> HTTPException:
    """작업공간 예외를 HTTP 로 옮긴다.

    InvalidPath 는 두 종류를 섞어 담는다 — 루트 밖(공격)과 잘못된 이름(오타).
    둘 다 400 으로 답하고 문구만 그대로 전한다. 나누어 알리면 그 자체가 파일
    존재 여부를 떠보는 수단이 된다.
    """
    if isinstance(error, WorkspaceNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="찾을 수 없습니다"
        )
    if isinstance(error, WorkspaceConflict):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="같은 이름이 이미 있습니다"
        )
    if isinstance(error, QuotaExceeded):
        return HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="저장 공간이 부족합니다",
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get("")
async def index(workspace: Workspace = Depends(current_workspace)) -> TreeResponse:
    """모든 층을 편 목록. 화면에서 트리로 다시 조립한다."""
    try:
        entries = workspace.tree()
    except (InvalidPath, WorkspaceNotFound) as error:
        raise _handle(error) from None
    return TreeResponse(
        entries=[
            EntryResponse(
                path=entry.path,
                name=entry.name,
                is_dir=entry.is_dir,
                size_bytes=entry.size_bytes,
            )
            for entry in entries
        ]
    )


@router.get("/usage")
async def usage(workspace: Workspace = Depends(current_workspace)) -> UsageResponse:
    report = workspace.usage()
    return UsageResponse(
        used_bytes=report.used_bytes,
        quota_bytes=report.quota_bytes,
        remaining_bytes=report.remaining_bytes,
    )


@router.get("/content")
async def read(
    path: str = Query(min_length=1, max_length=_MAX_PATH_CHARS),
    workspace: Workspace = Depends(current_workspace),
) -> ContentResponse:
    try:
        return ContentResponse(path=path, content=workspace.read(path))
    except (InvalidPath, WorkspaceNotFound, WorkspaceConflict) as error:
        raise _handle(error) from None


@router.put("/content")
async def write(
    payload: WriteRequest,
    workspace: Workspace = Depends(current_workspace),
) -> ContentResponse:
    try:
        workspace.write(payload.path, payload.content)
    except (
        InvalidPath,
        WorkspaceNotFound,
        WorkspaceConflict,
        QuotaExceeded,
    ) as error:
        raise _handle(error) from None
    return ContentResponse(path=payload.path, content=payload.content)


@router.post("/folder", status_code=status.HTTP_201_CREATED)
async def make_folder(
    payload: FolderRequest,
    workspace: Workspace = Depends(current_workspace),
) -> EntryResponse:
    try:
        workspace.make_folder(payload.path)
    except (InvalidPath, WorkspaceNotFound, WorkspaceConflict) as error:
        raise _handle(error) from None
    return EntryResponse(
        path=payload.path,
        name=payload.path.rsplit("/", 1)[-1],
        is_dir=True,
        size_bytes=0,
    )


@router.post("/rename")
async def rename(
    payload: RenameRequest,
    workspace: Workspace = Depends(current_workspace),
) -> EntryResponse:
    """이름 바꾸기와 옮기기는 같은 연산이다."""
    try:
        workspace.rename(payload.path, payload.destination)
    except (InvalidPath, WorkspaceNotFound, WorkspaceConflict) as error:
        raise _handle(error) from None
    return EntryResponse(
        path=payload.destination,
        name=payload.destination.rsplit("/", 1)[-1],
        is_dir=False,
        size_bytes=0,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(
    path: str = Query(min_length=1, max_length=_MAX_PATH_CHARS),
    workspace: Workspace = Depends(current_workspace),
) -> None:
    """파일이나 폴더를 지운다. 폴더는 안의 것까지 함께 사라진다."""
    try:
        workspace.delete(path)
    except (InvalidPath, WorkspaceNotFound, WorkspaceConflict) as error:
        raise _handle(error) from None


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def run(
    payload: RunRequest,
    workspace: Workspace = Depends(current_workspace),
    session: Session = Depends(current_session),
    queue: JobQueue = Depends(get_queue),
    settings: Settings = Depends(get_app_settings),
) -> RunResponse:
    """작업공간의 파일 하나를 실행한다.

    **제출 시점의 내용을 스냅샷으로 함께 저장한다.** 경로만 두면 실행이 끝나기
    전에 사용자가 파일을 고쳤을 때 결과와 입력이 어긋난다.
    """
    try:
        source = workspace.read(payload.path)
    except (InvalidPath, WorkspaceNotFound, WorkspaceConflict) as error:
        raise _handle(error) from None

    # 경로는 서버가 정한다. 사용자 입력이 섞이면 경로 탈출로 이어진다.
    workdir = Path(settings.jobs_root).resolve() / f"job-{uuid4().hex}"

    job = await queue.enqueue(
        owner_id=int(session.user_id),
        source_revision_id=None,
        workdir=str(workdir),
        source_path=payload.path,
        source=source,
    )

    return RunResponse(
        id=job.id, status=job.status.value, source_path=payload.path
    )
