"""관리자 전용 엔드포인트.

지금은 초대 코드 발급·조회·회수뿐이다. 모든 경로가 require_admin 을 지나므로
일반 사용자에게는 존재 자체가 404/403 로만 보인다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.auth.invites import (
    DEFAULT_MAX_USES,
    issue_invite,
    list_invites,
    revoke_invite,
)
from app.auth.models import Session

router = APIRouter(prefix="/admin", tags=["admin"])

#: 초대 유효기간 상한. 무기한 코드는 사실상 가입 개방과 같다.
_MAX_VALID_DAYS = 90
#: 한 코드로 받을 수 있는 인원 상한. 동시 접속 정원을 크게 넘길 이유가 없다.
_MAX_USES_LIMIT = 10


class IssueInviteRequest(BaseModel):
    max_uses: int = Field(default=DEFAULT_MAX_USES, ge=1, le=_MAX_USES_LIMIT)
    valid_days: int = Field(default=7, ge=1, le=_MAX_VALID_DAYS)


class IssuedInvite(BaseModel):
    id: int
    #: 평문 코드. **이 응답에서만** 볼 수 있고 다시 조회할 수 없다.
    code: str
    expires_at: datetime
    max_uses: int


class InviteSummary(BaseModel):
    id: int
    expires_at: datetime
    max_uses: int
    used_count: int
    revoked: bool
    #: 지금 쓸 수 있는지. 만료·소진·회수를 한 번에 판단해 준다.
    usable: bool


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    payload: IssueInviteRequest,
    session: Session = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> IssuedInvite:
    """초대 코드를 발급한다. 평문은 이 응답에서만 볼 수 있다."""
    invite, code = await issue_invite(
        db,
        created_by=int(session.user_id),
        max_uses=payload.max_uses,
        valid_for=timedelta(days=payload.valid_days),
    )
    return IssuedInvite(
        id=invite.id,
        code=code,
        expires_at=invite.expires_at,
        max_uses=invite.max_uses,
    )


@router.get("/invites")
async def index(
    _: Session = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[InviteSummary]:
    """발급 이력. 평문 코드는 어디에도 남아 있지 않으므로 돌려줄 수 없다."""
    now = datetime.now(timezone.utc)
    return [
        InviteSummary(
            id=invite.id,
            expires_at=invite.expires_at,
            max_uses=invite.max_uses,
            used_count=invite.used_count,
            revoked=invite.revoked_at is not None,
            usable=(
                invite.revoked_at is None
                and _as_utc(invite.expires_at) > now
                and invite.used_count < invite.max_uses
            ),
        )
        for invite in await list_invites(db)
    ]


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invite(
    invite_id: int,
    _: Session = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """즉시 회수한다. 재배포나 재시작이 필요 없어야 한다."""
    if not await revoke_invite(db, invite_id):
        # 없는 것과 이미 회수된 것을 구분하지 않는다. 어느 쪽이든 결과는 같다.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="초대를 찾을 수 없거나 이미 회수되었습니다",
        )


def _as_utc(value: datetime) -> datetime:
    """SQLite 는 타임존을 잃어버린 naive datetime 을 돌려준다."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
