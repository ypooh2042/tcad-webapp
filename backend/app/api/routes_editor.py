"""편집기 상태 — 열어 둔 탭, 커서, 저장하지 않은 초안.

세션은 30분 유휴로 끊긴다. 다시 들어왔을 때 빈 화면이면 어느 파일을 보고
있었는지, 어디까지 고쳤는지 사용자가 기억해서 되짚어야 한다.

**저장하지 않은 내용까지 맡아 둔다.** 탭을 옮길 때마다 저장을 강요하면 잠깐
다른 파일을 들춰 보는 일조차 번거롭고, 저장은 곧 실행 대상이 바뀐다는 뜻이라
가볍게 시킬 일이 아니다.

여기 담기는 것은 **사용자가 쓴 코드**다. 소유자 외에는 절대 읽히면 안 되므로
모든 경로가 세션의 user_id 로만 조회한다.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_session, get_app_settings, get_db
from app.auth.models import Role, Session
from app.core.config import Settings
from app.db.models import EditorState
from app.workspace.factory import workspace_for

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/editor", tags=["editor"])

#: 한 번에 열어 둘 수 있는 탭 수. 상한이 없으면 한 요청으로 DB 한 행을
#: 무한히 키울 수 있다. 스무 개면 실제 작업에서 부딪히지 않는다.
_MAX_TABS = 20

#: 초안 하나의 길이. 파일 저장 상한과 같은 값이다 — 저장할 수 있는 것보다
#: 작게 잡으면 정작 큰 파일을 고치는 동안 초안이 보관되지 않는다.
_MAX_DRAFT_CHARS = 200_000

_MAX_PATH_CHARS = 1024


class CursorPosition(BaseModel):
    """1-based 줄·칸. Monaco 가 쓰는 규약을 그대로 따른다."""

    line: int = Field(ge=1)
    column: int = Field(default=1, ge=1)


class OpenTab(BaseModel):
    path: str = Field(min_length=1, max_length=_MAX_PATH_CHARS)
    #: 저장하지 않은 편집 내용. None 이면 파일 그대로라는 뜻이다.
    draft: str | None = Field(default=None, max_length=_MAX_DRAFT_CHARS)
    cursor: CursorPosition | None = None


class EditorStateBody(BaseModel):
    tabs: list[OpenTab] = Field(default_factory=list, max_length=_MAX_TABS)
    #: 지금 보고 있는 탭. tabs 안에 없으면 서버가 바로잡는다.
    active: str | None = Field(default=None, max_length=_MAX_PATH_CHARS)


EMPTY = EditorStateBody()


@router.get("/state")
async def read_state(
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> EditorStateBody:
    """마지막으로 남긴 편집기 상태.

    **없는 파일을 가리키는 탭은 걸러서 내보낸다.** 지우거나 이름을 바꾼 파일의
    탭이 남아 있으면 들어올 때마다 열기에 실패하고, 사용자는 그것을 닫는
    일부터 해야 한다.
    """
    row = await db.get(EditorState, int(session.user_id))
    if row is None:
        return EMPTY

    try:
        stored = EditorStateBody.model_validate_json(row.state)
    except ValueError:
        # 옛 형식이거나 손상된 값. 화면을 못 띄우는 것보다 빈 상태가 낫다.
        logger.warning("편집기 상태를 읽지 못했습니다: user=%s", session.user_id)
        return EMPTY

    return _without_missing_files(stored, session, settings)


@router.put("/state", status_code=status.HTTP_204_NO_CONTENT)
async def write_state(
    body: EditorStateBody,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """편집기 상태를 통째로 바꾼다.

    부분 갱신을 두지 않는 이유는 탭 목록·활성 탭·초안이 **서로 맞아야 하는 한
    벌**이기 때문이다. 따로 갱신하면 활성 탭이 없는 탭을 가리키는 중간 상태가
    생긴다.
    """
    normalised = _with_valid_active(body)
    payload = normalised.model_dump_json()

    user_id = int(session.user_id)
    row = await db.get(EditorState, user_id)
    if row is None:
        db.add(EditorState(user_id=user_id, state=payload))
    else:
        row.state = payload
    await db.commit()


def _with_valid_active(state: EditorStateBody) -> EditorStateBody:
    """활성 탭이 실제로 열려 있는 것을 가리키게 만든다."""
    paths = [tab.path for tab in state.tabs]
    if state.active in paths:
        return state
    return EditorStateBody(tabs=state.tabs, active=paths[0] if paths else None)


def _without_missing_files(
    state: EditorStateBody, session: Session, settings: Settings
) -> EditorStateBody:
    space = workspace_for(
        settings, int(session.user_id), session.role is Role.ADMIN
    )
    present = {entry.path for entry in space.tree() if not entry.is_dir}
    alive = [tab for tab in state.tabs if tab.path in present]
    if len(alive) == len(state.tabs):
        return _with_valid_active(state)
    return _with_valid_active(EditorStateBody(tabs=alive, active=state.active))
