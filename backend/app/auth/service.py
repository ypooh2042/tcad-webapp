"""회원가입과 로그인.

사용자 열거(user enumeration)를 막는 것이 이 모듈의 주된 관심사다. "없는
계정"과 "틀린 비밀번호"를 구분해서 알려주면 공격자가 가입된 이메일 목록을
만들 수 있다. 응답도, 걸리는 시간도 구분되면 안 된다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.db.models import User

#: 존재하지 않는 계정에 대해서도 검증을 수행하기 위한 더미 해시.
#: 이것이 없으면 "계정 없음" 경로가 눈에 띄게 빨라져 타이밍만으로 가입 여부가
#: 드러난다. 어떤 비밀번호와도 일치하지 않는 값이다.
_DUMMY_HASH = hash_password("dummy-password-for-constant-time-comparison")


class EmailAlreadyRegistered(Exception):
    """이미 가입된 이메일."""


async def register_user(
    session: AsyncSession,
    email: str,
    password: str,
    role: Role = Role.USER,
    invite_code_id: int | None = None,
) -> User:
    """계정을 만든다.

    Raises:
        EmailAlreadyRegistered: 이미 쓰이는 이메일일 때. 호출부는 이 사실을
            그대로 노출할지 신중히 결정해야 한다(가입 폼에서는 불가피하지만,
            로그인 경로에서는 절대 구분해서 알리면 안 된다).
    """
    normalized = _normalize_email(email)
    existing = await session.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        raise EmailAlreadyRegistered(normalized)

    user = User(
        email=normalized,
        password_hash=hash_password(password),
        role=role.value,
        invite_code_id=invite_code_id,
    )
    session.add(user)
    await session.commit()
    return user


async def authenticate(
    session: AsyncSession, email: str, password: str
) -> User | None:
    """자격 증명을 확인한다. 실패하면 이유를 구분하지 않고 None 을 돌려준다."""
    user = await session.scalar(
        select(User).where(User.email == _normalize_email(email))
    )

    if user is None:
        # 계정이 없어도 검증을 수행해 응답 시간을 비슷하게 유지한다.
        verify_password(_DUMMY_HASH, password)
        return None

    if not verify_password(user.password_hash, password):
        return None

    if not user.is_active:
        return None

    # 평문을 아는 유일한 시점이라 여기서 해시 파라미터를 갱신한다.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        await session.commit()

    return user


def _normalize_email(email: str) -> str:
    """대소문자와 앞뒤 공백 차이로 중복 계정이 생기지 않게 한다."""
    return email.strip().lower()
