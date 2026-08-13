"""요청 의존성.

세션 유효성 검사가 여기 있다. 매 요청마다 활동 시각을 갱신하므로, 사용자가
계속 쓰고 있으면 30분 타이머가 계속 뒤로 밀린다. 반대로 30분간 요청이 없으면
다음 요청에서 만료된다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import set_session_cookie
from app.auth.models import Session
from app.auth.policy import SessionPolicy
from app.auth.store import SessionStore
from app.core.config import Settings
from app.jobs.queue import JobQueue

if TYPE_CHECKING:
    from app.db.models import Artifact, Job


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    maker = request.app.state.sessionmaker
    async with maker() as session:
        yield session


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_session_policy(request: Request) -> SessionPolicy:
    return request.app.state.session_policy


def get_queue(request: Request) -> "JobQueue":
    return request.app.state.queue


def get_app_settings(request: Request) -> Settings:
    """app.state 에 담긴 설정을 돌려준다.

    `get_settings()` 를 직접 의존성으로 쓰면 안 된다. 그쪽은 lru_cache 된
    전역값이라 테스트나 다중 인스턴스가 주입한 설정을 무시한다. 실제로 이
    실수 때문에 테스트 환경에서도 쿠키에 Secure 가 붙어 http 로는 세션이
    전달되지 않았다.
    """
    return request.app.state.settings


async def current_session(
    response: Response,
    tcad_session: str | None = Cookie(default=None),
    store: SessionStore = Depends(get_session_store),
    policy: SessionPolicy = Depends(get_session_policy),
    settings: Settings = Depends(get_app_settings),
) -> Session:
    """현재 로그인 세션. 없거나 만료됐으면 401.

    유효한 세션이면 활동 시각을 갱신한다. 이것이 "30분간 동작이 없으면 강제
    로그아웃" 규칙의 실제 동작 지점이다.

    **쿠키도 함께 다시 심는다.** 서버에서만 시간을 미루면 브라우저의 쿠키는
    로그인 시점 기준으로 만료되어, 계속 쓰고 있는데도 로그인 30분 뒤에 딱
    끊긴다. 미루는 쪽과 기억하는 쪽이 같이 움직여야 한다.
    """
    if not tcad_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다"
        )

    try:
        session = await policy.touch(
            store, tcad_session, now=datetime.now(timezone.utc)
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료되었습니다. 다시 로그인해 주세요.",
        ) from None

    set_session_cookie(response, session, settings, policy)
    return session


async def require_admin(session: Session = Depends(current_session)) -> Session:
    """관리자 전용 엔드포인트용."""
    if not session.role.is_exempt_from_limits:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="권한이 없습니다"
        )
    return session


async def owned_job(
    job_id: int,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> "Job":
    """소유 확인을 마친 잡.

    남의 잡은 "없음"과 **같은** 404 로 응답한다. 403 으로 구분해 답하면 id 를
    훑어 다른 사용자의 잡이 존재하는지 알아낼 수 있고, 잡 로그에는 사용자가 쓴
    코드와 실행 결과가 그대로 들어 있다.
    """
    from app.db.models import Job

    job = await db.get(Job, job_id)
    if job is None or job.owner_id != int(session.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="잡을 찾을 수 없습니다"
        )
    return job


async def owned_artifact(
    sequence: int,
    job: "Job" = Depends(owned_job),
    db: AsyncSession = Depends(get_db),
) -> "Artifact":
    """소유 확인을 마친 산출물."""
    from sqlalchemy import select

    from app.db.models import Artifact

    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.job_id == job.id, Artifact.sequence == sequence
        )
    )
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="산출물을 찾을 수 없습니다"
        )
    return artifact
