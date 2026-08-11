"""Alembic 실행 환경.

접속 URL 은 alembic.ini 가 아니라 앱 설정(Settings)에서 가져온다. ini 는 커밋되는
파일이라 여기에 URL 을 적으면 운영 비밀번호가 레포에 남는다. 설정을 거치면
앱과 마이그레이션이 언제나 같은 DB 를 보게 되는 이점도 있다.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import Settings
from app.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 모델 전체가 여기에 물려 있어야 autogenerate 가 차이를 찾아낸다. app.db.models
# 를 import 하는 것만으로 모든 테이블이 이 metadata 에 등록된다.
target_metadata = Base.metadata

#: alembic.ini 의 자리표시자를 실제 URL 로 덮어쓴다. `-x db_url=...` 로 한 번만
#: 다르게 지정할 수도 있게 열어 둔다(테스트용 임시 DB 등).
_database_url = context.get_x_argument(as_dictionary=True).get(
    "db_url"
) or Settings().database_url
config.set_main_option("sqlalchemy.url", _database_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    """SQL 문만 출력한다. DB 에 연결하지 않는다."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # 타입 변경까지 감지한다. 이게 없으면 String(200) → String(500) 같은
        # 변경이 autogenerate 에서 조용히 누락된다.
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
