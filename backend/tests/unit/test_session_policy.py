"""세션 정책 테스트.

요구사항:
  - 동시 로그인 10명 제한
  - 로그인 후 30분간 동작이 없으면 강제 로그아웃
  - 관리자 계정은 위 두 제한을 모두 면제

시간에 의존하는 규칙이라 실제 sleep 대신 시계를 주입해 검증한다.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth.policy import SessionLimitExceeded, SessionPolicy
from app.auth.models import Role
from app.auth.store import InMemorySessionStore

T0 = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def policy() -> SessionPolicy:
    return SessionPolicy()


async def login(store, policy, user: str, at: datetime, role: Role = Role.USER):
    return await policy.open_session(store, user_id=user, role=role, now=at)


class TestDefaults:
    def test_matches_requested_limits(self, policy) -> None:
        assert policy.max_concurrent == 10
        assert policy.idle_timeout == timedelta(minutes=30)


class TestConcurrentLimit:
    async def test_allows_up_to_ten_users(self, store, policy) -> None:
        for i in range(10):
            await login(store, policy, f"user{i}", T0)
        assert len(await store.active_sessions(T0, policy.idle_timeout)) == 10

    async def test_rejects_eleventh_user(self, store, policy) -> None:
        for i in range(10):
            await login(store, policy, f"user{i}", T0)
        with pytest.raises(SessionLimitExceeded):
            await login(store, policy, "user10", T0)

    async def test_same_user_relogin_does_not_consume_extra_slot(
        self, store, policy
    ) -> None:
        """같은 사용자가 다시 로그인해도 정원을 두 번 차지하면 안 된다."""
        for i in range(10):
            await login(store, policy, f"user{i}", T0)
        await login(store, policy, "user0", T0 + timedelta(minutes=1))
        assert len(await store.active_sessions(T0, policy.idle_timeout)) == 10

    async def test_relogin_revokes_the_previous_session(self, store, policy) -> None:
        """1인 1세션. 그러지 않으면 세션이 무한히 쌓이고 정원 기준도 모호해진다."""
        first = await login(store, policy, "user0", T0)
        second = await login(store, policy, "user0", T0 + timedelta(minutes=1))

        assert await store.get(first.id) is None
        assert await store.get(second.id) is not None

    async def test_logout_frees_a_slot(self, store, policy) -> None:
        sessions = [await login(store, policy, f"user{i}", T0) for i in range(10)]
        await policy.close_session(store, sessions[0].id)
        await login(store, policy, "user10", T0)

    async def test_expired_session_frees_a_slot(self, store, policy) -> None:
        """자리를 비운 사용자가 정원을 영구히 점유하면 안 된다.

        30분이 지나 만료된 세션은 정원 계산에서 빠져야 새 사용자가 들어온다.
        """
        for i in range(10):
            await login(store, policy, f"user{i}", T0)
        later = T0 + timedelta(minutes=31)
        await login(store, policy, "user10", later)


class TestIdleTimeout:
    async def test_session_valid_before_timeout(self, store, policy) -> None:
        session = await login(store, policy, "user0", T0)
        assert policy.is_active(session, now=T0 + timedelta(minutes=29))

    async def test_session_expires_after_thirty_idle_minutes(self, store, policy) -> None:
        session = await login(store, policy, "user0", T0)
        assert not policy.is_active(session, now=T0 + timedelta(minutes=31))

    async def test_expiry_boundary_is_exclusive(self, store, policy) -> None:
        """정확히 30분 시점은 아직 살아 있다."""
        session = await login(store, policy, "user0", T0)
        assert policy.is_active(session, now=T0 + timedelta(minutes=30))

    async def test_activity_resets_the_timer(self, store, policy) -> None:
        session = await login(store, policy, "user0", T0)
        refreshed = await policy.touch(store, session.id, now=T0 + timedelta(minutes=25))
        assert policy.is_active(refreshed, now=T0 + timedelta(minutes=50))

    async def test_touching_expired_session_fails(self, store, policy) -> None:
        """만료된 세션은 되살아나면 안 된다."""
        session = await login(store, policy, "user0", T0)
        with pytest.raises(KeyError):
            await policy.touch(store, session.id, now=T0 + timedelta(minutes=31))

    async def test_idle_measured_from_last_activity_not_login(self, store, policy) -> None:
        """로그인 후 45분이 지났어도, 20분 시점에 활동했다면 아직 살아 있다."""
        session = await login(store, policy, "user0", T0)
        await policy.touch(store, session.id, now=T0 + timedelta(minutes=20))
        assert policy.is_active(
            await store.get(session.id), now=T0 + timedelta(minutes=45)
        )


class TestAdminExemption:
    async def test_admin_can_login_when_full(self, store, policy) -> None:
        for i in range(10):
            await login(store, policy, f"user{i}", T0)
        admin = await login(store, policy, "root", T0, role=Role.ADMIN)
        assert admin.role is Role.ADMIN

    async def test_admin_does_not_consume_a_user_slot(self, store, policy) -> None:
        """관리자가 정원을 차지하면 일반 사용자 10명이 못 들어온다."""
        await login(store, policy, "root", T0, role=Role.ADMIN)
        for i in range(10):
            await login(store, policy, f"user{i}", T0)

    async def test_admin_never_expires_from_idling(self, store, policy) -> None:
        admin = await login(store, policy, "root", T0, role=Role.ADMIN)
        assert policy.is_active(admin, now=T0 + timedelta(days=7))

    async def test_admin_session_still_closable(self, store, policy) -> None:
        """면제는 자동 만료에 대한 것이지 로그아웃까지 막지는 않는다."""
        admin = await login(store, policy, "root", T0, role=Role.ADMIN)
        await policy.close_session(store, admin.id)
        assert await store.get(admin.id) is None


class TestSessionIdentifiers:
    async def test_ids_are_unpredictable(self, store, policy) -> None:
        ids = {(await login(store, policy, f"user{i}", T0)).id for i in range(10)}
        assert len(ids) == 10
        assert all(len(session_id) >= 32 for session_id in ids)

    async def test_ids_are_not_derived_from_user_id(self, store, policy) -> None:
        session = await login(store, policy, "predictable-user", T0)
        assert "predictable-user" not in session.id


class TestImmutability:
    async def test_session_is_frozen(self, store, policy) -> None:
        session = await login(store, policy, "user0", T0)
        with pytest.raises(Exception):
            session.user_id = "someone-else"  # type: ignore[misc]

    async def test_touch_returns_new_object(self, store, policy) -> None:
        session = await login(store, policy, "user0", T0)
        refreshed = await policy.touch(store, session.id, now=T0 + timedelta(minutes=5))
        assert refreshed is not session
        assert refreshed.last_seen_at > session.last_seen_at
