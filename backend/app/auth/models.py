"""인증 도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum


class Role(Enum):
    """계정 권한.

    ADMIN 은 동시 접속 정원과 유휴 타임아웃을 모두 면제받는다.
    """

    USER = "user"
    ADMIN = "admin"

    @property
    def is_exempt_from_limits(self) -> bool:
        return self is Role.ADMIN


@dataclass(frozen=True, slots=True)
class Session:
    """로그인 세션.

    last_seen_at 은 마지막 활동 시각이다. 유휴 판정의 기준은 로그인 시각이
    아니라 이 값이다.
    """

    id: str
    user_id: str
    role: Role
    created_at: datetime
    last_seen_at: datetime

    def touched_at(self, now: datetime) -> Session:
        """활동 시각을 갱신한 새 세션을 반환한다(원본은 그대로)."""
        return replace(self, last_seen_at=now)
