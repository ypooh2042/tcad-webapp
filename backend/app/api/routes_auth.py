"""인증 엔드포인트."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    current_session,
    get_app_settings,
    get_db,
    get_session_policy,
    get_session_store,
)
from app.auth.models import Role, Session
from app.auth.policy import SessionLimitExceeded, SessionPolicy
from app.auth.service import EmailAlreadyRegistered, authenticate, register_user
from app.auth.store import SessionStore
from app.core.config import Settings

router = APIRouter(prefix="/auth", tags=["auth"])

#: 로그인 실패 시 항상 같은 문구를 쓴다. "없는 계정"과 "틀린 비밀번호"를
#: 구분해서 알리면 가입된 이메일을 알아낼 수 있다.
_INVALID_CREDENTIALS = "이메일 또는 비밀번호가 올바르지 않습니다"


class RegisterRequest(BaseModel):
    email: EmailStr
    #: 길이 하한만 강제한다. 복잡도 규칙은 오히려 예측 가능한 패턴을 유도한다.
    password: str = Field(min_length=12, max_length=1024)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    id: int
    email: str
    role: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    try:
        user = await register_user(db, payload.email, payload.password)
    except EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 가입된 이메일입니다",
        ) from None
    return UserResponse(id=user.id, email=user.email, role=user.role)


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    store: SessionStore = Depends(get_session_store),
    policy: SessionPolicy = Depends(get_session_policy),
    settings: Settings = Depends(get_app_settings),
) -> UserResponse:
    user = await authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS
        )

    try:
        session = await policy.open_session(
            store,
            user_id=str(user.id),
            role=Role(user.role),
            now=datetime.now(timezone.utc),
        )
    except SessionLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"동시 접속자가 정원({policy.max_concurrent}명)에 도달했습니다. "
                "잠시 후 다시 시도해 주세요."
            ),
        ) from None

    _set_session_cookie(response, session, settings, policy)
    return UserResponse(id=user.id, email=user.email, role=user.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: Session = Depends(current_session),
    store: SessionStore = Depends(get_session_store),
    policy: SessionPolicy = Depends(get_session_policy),
    settings: Settings = Depends(get_app_settings),
) -> None:
    await policy.close_session(store, session.id)
    response.delete_cookie(settings.session_cookie_name)


@router.get("/me")
async def me(
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    from app.db.models import User  # 순환 임포트 방지를 위해 지역 임포트

    user = await db.get(User, int(session.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return UserResponse(id=user.id, email=user.email, role=user.role)


def _set_session_cookie(
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
        max_age=int(policy.idle_timeout.total_seconds()),
        path="/",
    )
