"""실제 PostgreSQL·Redis 를 쓰는 통합 테스트용 픽스처.

compose.dev.yml 의 개발 컨테이너를 전제로 하되, 없으면 건너뛴다. 컨테이너가
꺼져 있다고 해서 나머지 테스트까지 실패로 보이면 안 되기 때문이다.

DB 는 테스트마다 새로 만들고 끝나면 지운다. 개발 DB 를 공유하면 마이그레이션
downgrade 테스트가 남의 데이터를 통째로 날린다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ADMIN_URL = os.environ.get(
    "TCAD_TEST_DATABASE_URL",
    "postgresql+asyncpg://tcad:tcad-dev-only@localhost:5433/tcad",
)

#: 개발용 세션과 섞이지 않도록 높은 DB 번호를 쓴다. 이 번호는 테스트가 통째로
#: 비운다.
REDIS_URL = os.environ.get("TCAD_TEST_REDIS_URL", "redis://localhost:6380/15")

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    """배포에서 쓰는 것과 같은 CLI 경로로 alembic 을 돌린다."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env={**os.environ, "TCAD_DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        timeout=120,
    )


async def _require_postgres() -> None:
    engine = create_async_engine(ADMIN_URL)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception as error:  # 연결 실패 예외 타입이 드라이버마다 다르다
        pytest.skip(f"PostgreSQL 에 연결할 수 없습니다: {error}")
    finally:
        await engine.dispose()


@pytest.fixture
async def scratch_database_url():
    """마이그레이션이 적용되지 않은 빈 데이터베이스."""
    await _require_postgres()

    name = f"tcad_test_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'create database "{name}"'))
    await admin.dispose()

    try:
        yield ADMIN_URL.rsplit("/", 1)[0] + "/" + name
    finally:
        admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
        async with admin.connect() as connection:
            await connection.execute(
                text(f'drop database if exists "{name}" with (force)')
            )
        await admin.dispose()


@pytest.fixture
async def migrated_database_url(scratch_database_url):
    """마이그레이션까지 적용된 데이터베이스.

    `create_all` 이 아니라 마이그레이션으로 만든다. 운영에 실제로 생기는 스키마
    위에서 검증해야 의미가 있다.
    """
    result = alembic("upgrade", "head", database_url=scratch_database_url)
    assert result.returncode == 0, result.stderr
    return scratch_database_url


@pytest.fixture
async def redis_url() -> str:
    """비어 있는 Redis DB. 앞 테스트가 남긴 세션이 정원 계산을 흐리지 않게 한다."""
    from redis.asyncio import Redis

    client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception as error:
        pytest.skip(f"Redis 에 연결할 수 없습니다: {error}")

    await client.flushdb()
    try:
        yield REDIS_URL
    finally:
        await client.flushdb()
        await client.aclose()
