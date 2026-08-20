"""Redis 세션 저장소.

키 하나에 세션 하나(`session:<id>`)를 JSON 으로 담고, 유휴 상한을 TTL 로 건다.
Redis 가 스스로 만료시키므로 별도 정리 작업이 필요 없고, 프로세스가 죽어도
세션이 남지 않는다. 관리자 세션은 면제 대상이라 TTL 을 걸지 않는다.

정원 계산에는 SCAN 을 쓴다. 활성 세션이 십여 개(정원 + 관리자) 수준이라
비용이 무시할 만하고, 별도 인덱스를 두면 TTL 로 사라진 세션과 어긋나 정원이
잘못 계산될 수 있다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from redis.asyncio import Redis

from app.auth.models import Role, Session

_KEY_PREFIX = "session:"


def _key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}"


def _serialize(session: Session) -> str:
    return json.dumps(
        {
            "id": session.id,
            "user_id": session.user_id,
            "role": session.role.value,
            "created_at": session.created_at.isoformat(),
            "last_seen_at": session.last_seen_at.isoformat(),
        }
    )


def _deserialize(payload: str) -> Session:
    raw = json.loads(payload)
    return Session(
        id=raw["id"],
        user_id=raw["user_id"],
        role=Role(raw["role"]),
        created_at=datetime.fromisoformat(raw["created_at"]),
        last_seen_at=datetime.fromisoformat(raw["last_seen_at"]),
    )


class RedisSessionStore:
    """운영용 세션 저장소."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, session_id: str) -> Session | None:
        payload = await self._redis.get(_key(session_id))
        return _deserialize(payload) if payload else None

    async def save(self, session: Session, ttl: timedelta | None = None) -> None:
        payload = _serialize(session)
        if ttl is None:
            await self._redis.set(_key(session.id), payload)
        else:
            await self._redis.set(_key(session.id), payload, ex=ttl)

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(_key(session_id))

    async def active_sessions(
        self, now: datetime, idle_timeout: timedelta
    ) -> tuple[Session, ...]:
        sessions: list[Session] = []
        async for key in self._redis.scan_iter(match=f"{_KEY_PREFIX}*"):
            payload = await self._redis.get(key)
            if not payload:
                # SCAN 과 GET 사이에 TTL 로 사라졌다. 정상적인 경합이다.
                continue
            session = _deserialize(payload)
            # TTL 이 이미 걸러주지만, 시계 오차나 TTL 없는 관리자 세션까지
            # 일관되게 판정하려면 여기서도 확인한다.
            if session.role.is_exempt_from_limits:
                sessions.append(session)
            elif now - session.last_seen_at <= idle_timeout:
                sessions.append(session)
        return tuple(sessions)
