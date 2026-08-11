"""초대 코드 발급과 사용.

코드는 SHA-256 으로 저장한다. argon2 를 쓰지 않는 이유는 models.InviteCode 의
설명 참조 — 솔트 때문에 조회가 불가능해지고, 가입 시도마다 전수 검증이 되어
DoS 벡터가 된다.

평문 코드는 발급 응답에서 **한 번만** 돌려준다. 다시 볼 수 없다.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InviteCode

#: 코드 엔트로피. 32바이트면 추측이 불가능하고, URL 에 붙여 보내기에도 짧다.
_CODE_BYTES = 32

DEFAULT_VALIDITY = timedelta(days=7)
DEFAULT_MAX_USES = 1


class InviteError(Exception):
    """초대 코드를 쓸 수 없는 모든 경우의 상위 타입."""


class InviteNotFound(InviteError):
    """그런 코드가 없다."""


class InviteExpired(InviteError):
    """기간이 지났다."""


class InviteExhausted(InviteError):
    """사용 횟수를 다 썼다."""


class InviteRevoked(InviteError):
    """관리자가 회수했다."""


def hash_code(code: str) -> str:
    """조회용 결정적 해시.

    같은 코드가 항상 같은 해시여야 인덱스로 한 번에 찾는다.
    """
    return hashlib.sha256(code.encode()).hexdigest()


async def issue_invite(
    session: AsyncSession,
    created_by: int | None,
    max_uses: int = DEFAULT_MAX_USES,
    valid_for: timedelta = DEFAULT_VALIDITY,
) -> tuple[InviteCode, str]:
    """초대 코드를 만든다.

    Returns:
        (저장된 초대, 평문 코드). 평문은 여기서만 볼 수 있다.
    """
    if max_uses < 1:
        raise ValueError("사용 횟수는 1 이상이어야 합니다")

    code = secrets.token_urlsafe(_CODE_BYTES)
    invite = InviteCode(
        code_hash=hash_code(code),
        expires_at=datetime.now(timezone.utc) + valid_for,
        max_uses=max_uses,
        used_count=0,
        created_by=created_by,
    )
    session.add(invite)
    await session.commit()
    return invite, code


async def redeem_invite(session: AsyncSession, code: str) -> InviteCode:
    """코드를 한 번 사용 처리한다.

    사용 조건을 **조건부 UPDATE 한 줄**로 확인한다. 먼저 읽고 나서 쓰면, 두
    사람이 같은 1회용 코드를 동시에 내밀었을 때 둘 다 used_count=0 을 보고 둘 다
    통과한다.

    Raises:
        InviteNotFound / InviteExpired / InviteExhausted / InviteRevoked
    """
    now = datetime.now(timezone.utc)

    result = await session.execute(
        update(InviteCode)
        .where(
            InviteCode.code_hash == hash_code(code),
            InviteCode.revoked_at.is_(None),
            InviteCode.expires_at > now,
            InviteCode.used_count < InviteCode.max_uses,
        )
        .values(used_count=InviteCode.used_count + 1)
    )

    if result.rowcount == 1:
        await session.commit()
        invite = await session.scalar(
            select(InviteCode).where(InviteCode.code_hash == hash_code(code))
        )
        return invite

    await session.rollback()
    # 통과하지 못한 이유를 알려면 다시 읽어야 한다. 실패 경로라 비용은 문제되지
    # 않고, "왜 안 되는지"를 말해 줄 수 있어야 사용자가 대처한다.
    invite = await session.scalar(
        select(InviteCode).where(InviteCode.code_hash == hash_code(code))
    )
    if invite is None:
        raise InviteNotFound(code)
    if invite.revoked_at is not None:
        raise InviteRevoked(invite.id)
    if _as_utc(invite.expires_at) <= now:
        raise InviteExpired(invite.id)
    raise InviteExhausted(invite.id)


async def revoke_invite(session: AsyncSession, invite_id: int) -> bool:
    """즉시 회수한다. 행은 지우지 않는다 — 발급 이력이 남아야 한다."""
    result = await session.execute(
        update(InviteCode)
        .where(InviteCode.id == invite_id, InviteCode.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return result.rowcount == 1


async def list_invites(session: AsyncSession) -> tuple[InviteCode, ...]:
    result = await session.execute(
        select(InviteCode).order_by(InviteCode.created_at.desc(), InviteCode.id.desc())
    )
    return tuple(result.scalars().all())


def _as_utc(value: datetime) -> datetime:
    """SQLite 는 타임존을 잃어버린 naive datetime 을 돌려준다."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
