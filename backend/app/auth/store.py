"""세션 저장소.

정책(policy.py)은 저장 방식을 몰라야 한다. 운영에서는 Redis, 테스트에서는 메모리
구현을 쓴다.

인터페이스가 async 인 이유: 요청 핸들러가 async 인데 동기 Redis 호출을 섞으면
이벤트 루프가 막힌다. 잡 상태 조회처럼 자주 불리는 경로에서 특히 문제가 된다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from app.auth.models import Session


class SessionStore(Protocol):
    """세션 보관소가 제공해야 하는 연산."""

    async def get(self, session_id: str) -> Session | None: ...

    async def save(self, session: Session, ttl: timedelta | None) -> None:
        """세션을 저장한다.

        ttl 이 None 이면 만료시키지 않는다(관리자 세션). 그 외에는 저장소가
        스스로 만료시켜, 정리 작업 없이도 유휴 세션이 사라지게 한다.
        """
        ...

    async def delete(self, session_id: str) -> None: ...

    async def active_sessions(
        self, now: datetime, idle_timeout: timedelta
    ) -> tuple[Session, ...]:
        """만료되지 않은 세션만 돌려준다.

        정원 계산이 이 결과에 의존한다. 만료된 세션이 섞이면 자리를 비운
        사용자가 정원을 영구히 점유한다.
        """
        ...


class InMemorySessionStore:
    """테스트용. 프로세스 밖에서 공유되지 않으므로 운영에는 쓰지 않는다."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def save(self, session: Session, ttl: timedelta | None = None) -> None:
        self._sessions[session.id] = session

    async def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def active_sessions(
        self, now: datetime, idle_timeout: timedelta
    ) -> tuple[Session, ...]:
        return tuple(
            session
            for session in self._sessions.values()
            if session.role.is_exempt_from_limits
            or now - session.last_seen_at <= idle_timeout
        )
