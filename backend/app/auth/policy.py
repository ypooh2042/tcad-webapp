"""세션 정책.

요구사항 그대로:
  - 동시 로그인 5명 제한
  - 로그인 후 30분간 동작이 없으면 강제 로그아웃
  - 관리자 계정은 위 두 제한을 모두 면제

시각은 인자로 받는다. 내부에서 `datetime.now()` 를 부르면 시간에 의존하는 규칙을
테스트할 방법이 sleep 밖에 남지 않는다.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.auth.models import Role, Session
from app.auth.store import SessionStore

#: 세션 ID 바이트 수. 추측 가능한 ID 는 곧 세션 탈취로 이어진다.
_SESSION_ID_BYTES = 32


class SessionLimitExceeded(Exception):
    """동시 접속 정원이 찼을 때."""


@dataclass(frozen=True, slots=True)
class Occupancy:
    """지금 정원을 얼마나 쓰고 있는지.

    `occupied` 의 단위는 **세션이 아니라 사람**이다. 로그인 판정이 사람 단위로
    이뤄지므로(한 사람이 다시 로그인해도 자리를 두 번 차지하지 않는다), 화면에
    보여주는 수도 같은 기준이어야 한다. 기준이 다르면 "4/5" 를 보고 들어오려던
    사람이 거절당한다.
    """

    occupied: int
    capacity: int
    #: 접속 중인 관리자 수. 정원 **밖**이라 occupied 에 섞지 않는다. 그래도
    #: 세어서 알려주는 이유는, 섞지 않으면 "1/5" 인데 실제로는 세 명이 쓰고
    #: 있는 상황을 설명할 길이 없기 때문이다.
    admins: int

    @property
    def is_full(self) -> bool:
        return self.occupied >= self.capacity


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    max_concurrent: int = 5
    idle_timeout: timedelta = timedelta(minutes=30)
    #: 관리자 쿠키 수명. 관리자는 유휴 만료를 면제받아 서버 세션이 죽지 않는데,
    #: 쿠키에까지 유휴 상한을 걸면 브라우저 쪽에서만 30분마다 끊겨 면제가
    #: 무의미해진다 — 실제로 30분마다 다시 로그인해야 했다.
    admin_cookie_lifetime: timedelta = timedelta(days=30)

    def is_active(self, session: Session, now: datetime) -> bool:
        """유휴 시간이 상한을 넘지 않았는지. 관리자는 항상 활성이다.

        I/O 가 없는 순수 판정이라 동기로 둔다.
        """
        if session.role.is_exempt_from_limits:
            return True
        return now - session.last_seen_at <= self.idle_timeout

    def ttl_for(self, role: Role) -> timedelta | None:
        """저장소에 걸 만료 시간. 관리자는 만료시키지 않는다."""
        return None if role.is_exempt_from_limits else self.idle_timeout

    def cookie_max_age(self, role: Role) -> int:
        """브라우저에 걸 쿠키 수명(초).

        저장소 TTL 과 짝을 이뤄야 한다. 서버가 세션을 살려 둬도 **브라우저가
        쿠키를 버리면 사용자에게는 로그아웃과 같다.**

        일반 사용자는 유휴 상한이 곧 수명이고, 요청마다 다시 심어 갱신한다.
        관리자는 만료가 없으므로 쿠키에만 유한한 수명이 남는데, 그걸 30분으로
        두면 면제가 사라진다.
        """
        lifetime = (
            self.admin_cookie_lifetime
            if role.is_exempt_from_limits
            else self.idle_timeout
        )
        return int(lifetime.total_seconds())

    async def open_session(
        self,
        store: SessionStore,
        user_id: str,
        role: Role,
        now: datetime,
    ) -> Session:
        """로그인. 정원이 찼으면 거절한다.

        Raises:
            SessionLimitExceeded: 일반 사용자이고 정원이 찼을 때.
        """
        if not role.is_exempt_from_limits:
            await self._require_free_slot(store, user_id, now)

        # 1인 1세션. 재로그인하면 이전 세션을 무효화한다. 그러지 않으면 한
        # 사용자가 세션을 무한히 쌓을 수 있고, 동시 접속 정원의 기준도
        # 세션 수인지 사람 수인지 모호해진다.
        await self._revoke_existing(store, user_id, now)

        session = Session(
            id=secrets.token_urlsafe(_SESSION_ID_BYTES),
            user_id=user_id,
            role=role,
            created_at=now,
            last_seen_at=now,
        )
        await store.save(session, self.ttl_for(role))
        return session

    async def touch(
        self, store: SessionStore, session_id: str, now: datetime
    ) -> Session:
        """활동을 기록해 유휴 타이머를 되돌린다.

        Raises:
            KeyError: 세션이 없거나 이미 만료됐을 때. 만료된 세션을 되살리면
                30분 규칙이 무력화된다.
        """
        session = await store.get(session_id)
        if session is None:
            raise KeyError(f"세션을 찾을 수 없습니다: {session_id}")
        if not self.is_active(session, now):
            await store.delete(session_id)
            raise KeyError("세션이 만료되었습니다")

        refreshed = session.touched_at(now)
        await store.save(refreshed, self.ttl_for(refreshed.role))
        return refreshed

    async def close_session(self, store: SessionStore, session_id: str) -> None:
        """로그아웃. 관리자 세션도 닫을 수 있다(면제는 자동 만료에 한정)."""
        await store.delete(session_id)

    async def occupancy(self, store: SessionStore, now: datetime) -> Occupancy:
        """정원 사용 현황.

        로그인 판정(`_require_free_slot`)과 **같은 셈법을 써야 한다.** 다르게
        세면 화면이 자리가 있다고 말한 순간에 서버가 거절한다.
        """
        active = await store.active_sessions(now, self.idle_timeout)
        admins = {
            session.user_id
            for session in active
            if session.role.is_exempt_from_limits
        }
        return Occupancy(
            occupied=len(_occupants(active)),
            capacity=self.max_concurrent,
            admins=len(admins),
        )

    async def _revoke_existing(
        self, store: SessionStore, user_id: str, now: datetime
    ) -> None:
        for session in await store.active_sessions(now, self.idle_timeout):
            if session.user_id == user_id:
                await store.delete(session.id)

    async def _require_free_slot(
        self, store: SessionStore, user_id: str, now: datetime
    ) -> None:
        occupants = _occupants(
            await store.active_sessions(now, self.idle_timeout)
        )
        # 이미 접속 중인 사용자의 재로그인은 새 자리를 차지하지 않는다.
        if user_id in occupants:
            return
        if len(occupants) >= self.max_concurrent:
            raise SessionLimitExceeded(
                f"동시 접속 정원({self.max_concurrent}명)이 찼습니다"
            )


def _occupants(sessions: tuple[Session, ...]) -> set[str]:
    """정원을 차지하고 있는 사람들.

    로그인 판정과 현황 표시가 **이 함수 하나를 공유해야 한다.** 각자 세면 언젠가
    어긋나고, 그때 화면은 자리가 있다고 말하는데 서버는 거절한다.

    세션이 아니라 사용자 id 를 모은다. 관리자는 정원 밖이라 빠진다.
    """
    return {
        session.user_id
        for session in sessions
        if not session.role.is_exempt_from_limits
    }
