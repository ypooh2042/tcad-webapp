"""세션 쿠키를 심는 한 곳.

로그인할 때와 요청마다 갱신할 때가 **반드시 같은 규칙**이어야 한다. 두 곳에
따로 쓰면 한쪽만 고쳐지고, 그 차이는 "가끔 로그아웃된다"는 형태로만 드러나
원인을 찾기 어렵다.

수명은 여기서 정하지 않고 세션 정책에 묻는다. 저장소 TTL 과 쿠키 수명이 갈리면
서버는 세션을 살려 두는데 브라우저만 잊는 상태가 된다.
"""

from __future__ import annotations

from fastapi import Response

from app.auth.models import Session
from app.auth.policy import SessionPolicy
from app.core.config import Settings


def set_session_cookie(
    response: Response,
    session: Session,
    settings: Settings,
    policy: SessionPolicy,
) -> None:
    """세션 쿠키를 심는다.

    httponly: JS 가 읽지 못하게 해 XSS 로 세션이 새는 것을 막는다.
    samesite=lax: 외부 사이트에서 넘어온 POST 에 쿠키가 실리지 않게 해 CSRF 를 줄인다.
    secure: HTTPS 로만 전송. 운영에서는 반드시 켠다.
    """
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.id,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        max_age=policy.cookie_max_age(session.role),
        path="/",
    )
