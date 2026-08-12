"""인증 엔드포인트."""

from __future__ import annotations

import logging

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.throttle import (
    record_invite_failure,
    throttle_login,
    throttle_login_attempt,
    throttle_register,
)
from app.jobs.cache import discard_artifacts
from app.api.deps import (
    current_session,
    get_app_settings,
    get_db,
    get_session_policy,
    get_session_store,
)
from app.auth.invites import (
    InviteError,
    InviteExhausted,
    InviteExpired,
    InviteNotFound,
    InviteRevoked,
    redeem_invite,
)
from app.auth.models import Role, Session
from app.auth.passwords import MIN_PASSWORD_LENGTH
from app.auth.policy import SessionLimitExceeded, SessionPolicy
from app.auth.service import EmailAlreadyRegistered, authenticate, register_user
from app.auth.store import SessionStore
from app.core.config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

#: 로그인 실패 시 항상 같은 문구를 쓴다. "없는 계정"과 "틀린 비밀번호"를
#: 구분해서 알리면 가입된 이메일을 알아낼 수 있다.
_INVALID_CREDENTIALS = "이메일 또는 비밀번호가 올바르지 않습니다"


class RegisterRequest(BaseModel):
    email: EmailStr
    #: 길이 하한만 강제한다. 복잡도 규칙은 오히려 예측 가능한 패턴을 유도한다.
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)
    #: 초대 없이는 가입할 수 없다. 이 서버는 제출된 코드를 컨테이너에서
    #: 실행하므로, 누가 쓰는지 모르는 상태로 열어 둘 수 없다.
    invite_code: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    id: int
    email: str
    role: str


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(throttle_register)],
)
async def register(
    request: Request,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    try:
        invite = await redeem_invite(db, payload.invite_code)
    except InviteError as error:
        # 실패만 빈도 제한에 쌓는다. 성공한 가입은 유효한 코드를 소진했으므로
        # 초대 자체가 이미 상한 역할을 한다.
        record_invite_failure(request)
        # 왜 안 되는지는 알려준다(만료/소진/회수). 코드를 아는 사람에게만
        # 의미가 있는 정보이고, 모르면 대처할 방법이 없다.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_invite_message(error)
        ) from None

    try:
        user = await register_user(
            db, payload.email, payload.password, invite_code_id=invite.id
        )
    except EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 가입된 이메일입니다",
        ) from None
    return UserResponse(id=user.id, email=user.email, role=user.role)


@router.post("/login", dependencies=[Depends(throttle_login)])
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    store: SessionStore = Depends(get_session_store),
    policy: SessionPolicy = Depends(get_session_policy),
    settings: Settings = Depends(get_app_settings),
) -> UserResponse:
    # 계정별 시도 제한. IP 기준만으로는 무차별 대입을 못 막는다.
    throttle_login_attempt(payload.email)

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
    db: AsyncSession = Depends(get_db),
) -> None:
    await policy.close_session(store, session.id)

    # 산출물은 캐시다. 소스는 작업공간에 남아 있으므로 다시 실행하면 되살아난다.
    # 실패해도 로그아웃 자체는 끝내야 한다 — 세션은 이미 닫혔고, 여기서 500 을
    # 내면 사용자는 로그아웃이 안 된 줄 안다.
    try:
        await discard_artifacts(db, int(session.user_id))
    except Exception:  # noqa: BLE001 - 정리는 로그아웃을 막지 못한다
        logger.warning("산출물 정리 실패: user=%s", session.user_id, exc_info=True)

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


def _invite_message(error: InviteError) -> str:
    """초대 실패 사유를 사용자 문구로 옮긴다."""
    if isinstance(error, InviteExpired):
        return "초대 코드가 만료되었습니다. 새 코드를 요청해 주세요."
    if isinstance(error, InviteExhausted):
        return "이미 사용된 초대 코드입니다."
    if isinstance(error, InviteRevoked):
        return "회수된 초대 코드입니다."
    if isinstance(error, InviteNotFound):
        return "초대 코드가 올바르지 않습니다."
    return "초대 코드를 확인할 수 없습니다."
