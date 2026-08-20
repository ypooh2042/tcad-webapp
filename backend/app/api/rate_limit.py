"""요청 빈도 제한.

가장 급한 곳은 로그인이다. 막지 않으면 비밀번호를 무한히 시도할 수 있고,
argon2 검증이 무거워서 그 자체로 CPU 를 잡아먹는 공격이 된다 — 시뮬레이션과
코어를 나눠 쓰는 홈서버에서는 로그인 폭주만으로 잡이 밀린다.

프로세스 메모리에 둔다. Redis 로 옮기면 여러 워커가 한도를 공유하지만, 이
규모(접속 정원 5명, API 프로세스 1개)에서는 이득보다 복잡도가 크다. 여러 프로세스로
늘릴 때 다시 볼 것.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    """슬라이딩 윈도우 카운터.

    고정 창(fixed window)을 쓰면 창 경계에서 한도의 두 배가 통과한다. 창이
    바뀌는 순간에 맞춰 몰아치면 그대로 뚫리므로 슬라이딩으로 센다.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._now = now
        self._hits: dict[str, deque[float]] = {}

    def __len__(self) -> int:
        return len(self._hits)

    def allow(self, key: str) -> bool:
        """한 번 시도한 것으로 치고 통과 여부를 돌려준다."""
        if self.blocked(key):
            return False
        self.record(key)
        return True

    def blocked(self, key: str) -> bool:
        """한도에 걸렸는지만 본다. 횟수를 늘리지 않는다.

        "실패만 센다" 같은 정책을 만들려면 확인과 기록을 나눌 수 있어야 한다.
        """
        return len(self._prune(key, self._now())) >= self.limit

    def record(self, key: str) -> None:
        """한 번 썼다고 기록한다."""
        now = self._now()
        hits = self._prune(key, now)
        hits.append(now)
        self._hits[key] = hits
        self._collect_garbage(now)

    def retry_after(self, key: str) -> float:
        """언제 다시 시도할 수 있는지(초). 통과 가능하면 0.

        얼마나 기다려야 하는지 알려주지 않으면 클라이언트는 계속 두드린다.
        """
        now = self._now()
        hits = self._prune(key, now)
        if len(hits) < self.limit:
            return 0.0
        return max(0.0, hits[0] + self.window_seconds - now)

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key, deque())
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def _collect_garbage(self, now: float) -> None:
        """빈 기록을 버린다.

        키마다 기록을 영원히 들고 있으면, IP 를 바꿔가며 부을 때 메모리가 계속
        는다. 창이 지난 키는 더 볼 이유가 없다.
        """
        cutoff = now - self.window_seconds
        stale = [
            key
            for key, hits in self._hits.items()
            if not hits or hits[-1] <= cutoff
        ]
        for key in stale:
            del self._hits[key]
