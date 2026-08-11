"""엔드포인트별 빈도 제한 의존성.

한도는 "정상 사용자가 절대 부딪히지 않고, 자동화 공격은 확실히 걸리는" 선으로
잡는다. 사람이 로그인을 1분에 10번 넘게 시도할 일은 없다.

키는 클라이언트 IP 다. nginx 뒤에 있으므로 X-Forwarded-For 를 봐야 하는데,
**신뢰하는 프록시 뒤일 때만** 그렇다. 아무 헤더나 믿으면 공격자가 헤더를 바꿔
가며 한도를 무한히 우회한다.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.api.rate_limit import RateLimiter

#: 로그인(IP 기준). **동시 접속 정원(10명)보다 넉넉해야 한다.**
#:
#: 처음에 10회/분으로 잡았다가 테스트에서 걸렸다. 연구실 사람들은 같은 NAT
#: 뒤에 있으므로 서버가 보는 IP 가 하나다. 정원만큼 로그인하면 정원을 채우기도
#: 전에 429 를 맞는다. 여기서는 "폭주"만 막고, 무차별 대입은 아래 계정별
#: 한도가 맡는다.
_login_by_ip = RateLimiter(limit=60, window_seconds=60)

#: 로그인(계정 기준). 무차별 대입을 막는 실질적인 방어선이다. 한 계정에 대해
#: 15분에 10번이면 사람은 절대 부딪히지 않고 자동화는 확실히 걸린다.
_login_by_account = RateLimiter(limit=10, window_seconds=900)

#: 가입. 초대 코드를 무한히 넣어보지 못하게 한다.
_register = RateLimiter(limit=5, window_seconds=300)

#: 잡 제출. 큐가 동시 실행을 4개로 묶지만, 큐 자체는 무한히 길어질 수 있다.
_submit = RateLimiter(limit=30, window_seconds=60)


def client_key(request: Request) -> str:
    """빈도 제한의 기준이 되는 클라이언트 식별자.

    X-Forwarded-For 를 **읽지 않는다.** 그 헤더는 누구나 붙일 수 있어서, 믿으면
    값을 바꿔가며 한도를 무한히 우회할 수 있다. nginx 를 앞에 둘 때는
    uvicorn 을 `--proxy-headers --forwarded-allow-ips=127.0.0.1` 로 띄워
    **서버가 검증한** client.host 가 실제 IP 가 되게 한다.
    """
    return request.client.host if request.client else "unknown"


def _enforce(limiter: RateLimiter, request: Request, what: str) -> None:
    key = client_key(request)
    if limiter.allow(key):
        return

    wait = int(limiter.retry_after(key)) + 1
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"{what} 시도가 너무 잦습니다. {wait}초 후 다시 시도해 주세요.",
        # 클라이언트가 언제 다시 와야 하는지 알아야 계속 두드리지 않는다.
        headers={"Retry-After": str(wait)},
    )


async def throttle_login(request: Request) -> None:
    """IP 기준 폭주 차단. 계정별 방어는 throttle_login_attempt 가 맡는다."""
    _enforce(_login_by_ip, request, "로그인")


def throttle_login_attempt(email: str) -> None:
    """계정 하나에 대한 시도 횟수를 제한한다.

    IP 기준만으로는 무차별 대입을 못 막는다 — 공격자는 IP 를 바꿀 수 있고,
    반대로 정상 사용자들은 IP 를 공유한다. 노리는 계정은 바뀌지 않으므로
    계정을 키로 세는 것이 실제 방어선이다.

    Raises:
        HTTPException: 429. 계정 존재 여부는 드러나지 않는다 — 없는 계정도
            똑같이 센다.
    """
    key = email.strip().lower()
    if _login_by_account.allow(key):
        return

    wait = int(_login_by_account.retry_after(key)) + 1
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"로그인 시도가 너무 잦습니다. {wait}초 후 다시 시도해 주세요.",
        headers={"Retry-After": str(wait)},
    )


async def throttle_register(request: Request) -> None:
    _enforce(_register, request, "가입")


async def throttle_submit(request: Request) -> None:
    _enforce(_submit, request, "실행 요청")


def reset() -> None:
    """테스트에서 한도를 초기화한다. 프로세스 전역 상태라 격리가 필요하다."""
    for limiter in (_login_by_ip, _login_by_account, _register, _submit):
        limiter._hits.clear()
