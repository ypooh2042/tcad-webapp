"""레이트 리미팅.

가장 급한 곳은 로그인이다. 막지 않으면 비밀번호를 무한히 시도할 수 있고,
argon2 검증이 무겁기 때문에 그 자체로 CPU 를 잡아먹는 공격이 된다 — 시뮬레이션과
코어를 나눠 쓰는 홈서버에서는 로그인 폭주만으로 잡이 밀린다.

가입도 막아야 한다. 초대 코드를 무한히 넣어볼 수 있으면 초대 제도가 무의미해진다.
"""

from __future__ import annotations

import pytest

from app.api.rate_limit import RateLimiter


@pytest.fixture
def clock():
    """직접 굴리는 시계. 진짜로 기다리면 테스트가 몇 분씩 걸린다."""

    class Clock:
        now = 1000.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    return Clock()


class TestAllowing:
    def test_first_attempt_passes(self, clock) -> None:
        limiter = RateLimiter(limit=3, window_seconds=60, now=clock)

        assert limiter.allow("1.2.3.4")

    def test_up_to_the_limit_passes(self, clock) -> None:
        limiter = RateLimiter(limit=3, window_seconds=60, now=clock)

        assert [limiter.allow("k") for _ in range(3)] == [True, True, True]

    def test_beyond_the_limit_is_refused(self, clock) -> None:
        limiter = RateLimiter(limit=3, window_seconds=60, now=clock)
        for _ in range(3):
            limiter.allow("k")

        assert not limiter.allow("k")


class TestWindow:
    def test_window_slides(self, clock) -> None:
        limiter = RateLimiter(limit=2, window_seconds=60, now=clock)
        limiter.allow("k")
        limiter.allow("k")

        clock.advance(61)

        assert limiter.allow("k")

    def test_partial_expiry_frees_one_slot(self, clock) -> None:
        """고정 창이 아니라 슬라이딩이어야 한다. 고정 창이면 경계에서 두 배를
        허용한다."""
        limiter = RateLimiter(limit=2, window_seconds=60, now=clock)
        limiter.allow("k")
        clock.advance(30)
        limiter.allow("k")

        clock.advance(31)  # 첫 시도만 창 밖으로

        assert limiter.allow("k")
        assert not limiter.allow("k")


class TestIsolation:
    def test_keys_are_counted_separately(self, clock) -> None:
        """한 사람이 막혔다고 다른 사람까지 막히면 안 된다."""
        limiter = RateLimiter(limit=1, window_seconds=60, now=clock)
        limiter.allow("a")

        assert limiter.allow("b")

    def test_retry_after_tells_when_to_come_back(self, clock) -> None:
        limiter = RateLimiter(limit=1, window_seconds=60, now=clock)
        limiter.allow("k")
        clock.advance(20)

        assert limiter.retry_after("k") == pytest.approx(40, abs=1)

    def test_retry_after_is_zero_when_allowed(self, clock) -> None:
        limiter = RateLimiter(limit=2, window_seconds=60, now=clock)

        assert limiter.retry_after("k") == 0


class TestMemory:
    def test_old_keys_are_forgotten(self, clock) -> None:
        """키마다 기록을 영원히 들고 있으면 IP 를 바꿔가며 부으면 메모리가 는다."""
        limiter = RateLimiter(limit=1, window_seconds=60, now=clock)
        for i in range(100):
            limiter.allow(f"ip-{i}")

        clock.advance(61)
        limiter.allow("trigger-cleanup")

        assert len(limiter) <= 1
