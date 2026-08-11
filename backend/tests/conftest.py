"""모든 테스트에 공통으로 적용되는 설정."""

from __future__ import annotations

import pytest

from app.api import throttle


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """테스트마다 빈도 제한을 초기화한다.

    리미터는 프로세스 전역 상태다. 게다가 ASGITransport 로 보낸 요청에는
    request.client 가 없어서 모든 테스트가 같은 키("unknown")를 공유한다.
    초기화하지 않으면 앞 테스트가 쓴 횟수 때문에 뒤 테스트가 429 로 실패한다.

    프로덕션 동작을 끄는 것이 아니라 테스트 사이의 격리만 복구한다 — 한도 자체는
    test_throttle.py 에서 그대로 검증한다.
    """
    throttle.reset()
    yield
    throttle.reset()
