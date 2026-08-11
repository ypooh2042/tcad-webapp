"""FastAPI 애플리케이션.

의존성(DB, 세션 저장소, 정책)은 app.state 에 담아 두고 요청 시 꺼내 쓴다.
테스트에서 메모리 구현으로 갈아끼울 수 있어야 하기 때문이다.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import routes_auth, routes_jobs, routes_projects
from app.auth.policy import SessionPolicy
from app.auth.redis_store import RedisSessionStore
from app.core.config import Settings, get_settings
from app.jobs.queue import JobQueue


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.session_store = RedisSessionStore(redis)
    app.state.queue = JobQueue(
        app.state.sessionmaker, max_concurrent=settings.max_concurrent_jobs
    )

    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="TCAD Web", lifespan=lifespan)
    app.state.settings = settings or get_settings()
    app.state.session_policy = SessionPolicy()

    app.include_router(routes_auth.router, prefix="/api")
    app.include_router(routes_projects.router, prefix="/api")
    app.include_router(routes_jobs.router, prefix="/api")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
