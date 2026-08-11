"""마이그레이션이 모델 정의와 일치하는지 검증한다.

다른 테스트는 전부 `Base.metadata.create_all` 로 스키마를 만든다. 그래서 모델만
고치고 마이그레이션을 빠뜨려도 테스트는 전부 통과하고, 정작 운영 DB 에는 컬럼이
없어서 배포한 뒤에야 터진다. 이 테스트가 그 간극을 막는 유일한 지점이다.

실제 PostgreSQL 에 대고 돌린다. SQLite 로는 의미가 없다 — 타입도 제약도 다르게
번역되므로 운영에서 만들어질 스키마를 확인하지 못한다.
"""

from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base
from tests.integration.conftest import alembic

pytestmark = pytest.mark.integration


async def _inspect(database_url: str, fn):
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(fn)
    finally:
        await engine.dispose()


def _table_names(sync_connection) -> set[str]:
    return set(inspect(sync_connection).get_table_names())


class TestUpgrade:
    async def test_upgrade_head_succeeds_on_empty_database(
        self, scratch_database_url
    ) -> None:
        result = alembic("upgrade", "head", database_url=scratch_database_url)

        assert result.returncode == 0, result.stderr

    async def test_schema_matches_models(self, migrated_database_url) -> None:
        """마이그레이션이 만든 스키마와 모델 사이에 차이가 없어야 한다."""
        diff = await _inspect(
            migrated_database_url,
            lambda sync_connection: compare_metadata(
                MigrationContext.configure(
                    sync_connection, opts={"compare_type": True}
                ),
                Base.metadata,
            ),
        )

        assert diff == [], f"모델과 마이그레이션이 어긋납니다: {diff}"

    async def test_creates_every_model_table(self, migrated_database_url) -> None:
        tables = await _inspect(migrated_database_url, _table_names)

        assert set(Base.metadata.tables) <= tables


class TestDowngrade:
    async def test_downgrade_to_base_drops_every_table(
        self, migrated_database_url
    ) -> None:
        """downgrade 가 비어 있으면 롤백이 필요한 순간에 손을 쓸 수 없다."""
        result = alembic("downgrade", "base", database_url=migrated_database_url)

        assert result.returncode == 0, result.stderr

        tables = await _inspect(migrated_database_url, _table_names)

        # alembic_version 은 alembic 이 관리하는 표라 남아 있는 것이 정상이다.
        assert tables - {"alembic_version"} == set()
