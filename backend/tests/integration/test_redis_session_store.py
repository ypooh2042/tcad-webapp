"""Redis 세션 저장소 통합 테스트.

메모리 구현과 동작이 같아야 하고, 추가로 Redis 고유 동작(TTL 자동 만료,
프로세스 간 공유)을 확인한다.

실행: REDIS_URL 환경변수로 대상을 지정한다. 없으면 skip.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from redis.asyncio import Redis

from app.auth.models import Role
from app.auth.policy import SessionLimitExceeded, SessionPolicy
from app.auth.redis_store import RedisSessionStore

pytestmark = pytest.mark.integration

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6380/0")
T0 = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


async def _redis_available() -> bool:
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
        return True
    except Exception:
        return False
    finally:
        await client.aclose()


@pytest.fixture
async def store():
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip(f"Redis 에 접속할 수 없습니다: {REDIS_URL}")
    await client.flushdb()
    yield RedisSessionStore(client)
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def policy() -> SessionPolicy:
    return SessionPolicy()


class TestRoundTrip:
    async def test_session_survives_roundtrip(self, store, policy) -> None:
        created = await policy.open_session(
            store, user_id="user0", role=Role.USER, now=T0
        )
        loaded = await store.get(created.id)

        assert loaded == created

    async def test_missing_session_returns_none(self, store) -> None:
        assert await store.get("does-not-exist") is None

    async def test_role_survives_roundtrip(self, store, policy) -> None:
        created = await policy.open_session(
            store, user_id="root", role=Role.ADMIN, now=T0
        )
        assert (await store.get(created.id)).role is Role.ADMIN


async def fill(store, policy) -> list:
    """정원을 일반 사용자로 가득 채운다. 만든 세션들을 돌려준다."""
    return [
        await policy.open_session(store, f"user{i}", Role.USER, T0)
        for i in range(policy.max_concurrent)
    ]


class TestConcurrentLimit:
    async def test_enforces_the_cap(self, store, policy) -> None:
        await fill(store, policy)
        with pytest.raises(SessionLimitExceeded):
            await policy.open_session(store, "extra", Role.USER, T0)

    async def test_admin_bypasses_full_house(self, store, policy) -> None:
        await fill(store, policy)
        admin = await policy.open_session(store, "root", Role.ADMIN, T0)
        assert admin.role is Role.ADMIN

    async def test_logout_frees_slot(self, store, policy) -> None:
        sessions = await fill(store, policy)
        await policy.close_session(store, sessions[0].id)
        await policy.open_session(store, "extra", Role.USER, T0)

    async def test_occupancy_matches_the_gate(self, store, policy) -> None:
        """Redis 저장소에서도 현황과 로그인 판정이 같은 답을 내야 한다."""
        await fill(store, policy)
        occupancy = await policy.occupancy(store, T0)
        assert occupancy.is_full
        assert occupancy.occupied == policy.max_concurrent


class TestTimeToLive:
    async def test_user_session_has_ttl(self, store, policy) -> None:
        """TTL 이 없으면 프로세스가 죽었을 때 유휴 세션이 영원히 남는다."""
        session = await policy.open_session(store, "user0", Role.USER, T0)
        ttl = await store._redis.ttl(f"session:{session.id}")

        assert 0 < ttl <= policy.idle_timeout.total_seconds()

    async def test_admin_session_has_no_ttl(self, store, policy) -> None:
        """관리자는 유휴 만료 면제이므로 TTL 을 걸지 않는다."""
        session = await policy.open_session(store, "root", Role.ADMIN, T0)
        ttl = await store._redis.ttl(f"session:{session.id}")

        assert ttl == -1  # -1 = 키는 있으나 만료 없음

    async def test_touch_extends_ttl(self, store, policy) -> None:
        session = await policy.open_session(store, "user0", Role.USER, T0)
        await store._redis.expire(f"session:{session.id}", 60)

        await policy.touch(store, session.id, now=T0 + timedelta(minutes=5))
        ttl = await store._redis.ttl(f"session:{session.id}")

        assert ttl > 60


class TestCrossProcessSharing:
    async def test_second_client_sees_the_same_session(self, store, policy) -> None:
        """워커가 여러 프로세스로 뜨므로 세션이 공유돼야 한다."""
        created = await policy.open_session(store, "user0", Role.USER, T0)

        other_client = Redis.from_url(REDIS_URL, decode_responses=True)
        try:
            other_store = RedisSessionStore(other_client)
            assert await other_store.get(created.id) == created
        finally:
            await other_client.aclose()
