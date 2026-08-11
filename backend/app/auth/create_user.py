"""계정 생성 CLI.

    python -m app.auth.create_user --email a@example.com --admin

가입은 초대 코드를 요구한다. 그런데 코드를 발급하려면 관리자가 있어야 하고,
관리자가 되려면 가입해야 한다 — 이 순환을 여기서 끊는다. 첫 관리자를 만든 뒤
부터는 관리자 화면에서 초대를 발급하면 된다.

비밀번호는 인자로 받지 않는다. 명령행에 적으면 셸 히스토리와 프로세스 목록
(`ps`)에 그대로 남는다.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.models import Role
from app.auth.service import EmailAlreadyRegistered, register_user
from app.core.config import get_settings

#: routes_auth 의 RegisterRequest 와 같은 하한. 두 경로가 어긋나면 CLI 로만
#: 약한 비밀번호를 심을 수 있게 된다.
_MIN_PASSWORD_LENGTH = 12


def _read_password() -> str:
    password = getpass.getpass("비밀번호: ")
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise SystemExit(f"비밀번호는 {_MIN_PASSWORD_LENGTH}자 이상이어야 합니다")
    if password != getpass.getpass("비밀번호 확인: "):
        raise SystemExit("비밀번호가 일치하지 않습니다")
    return password


async def _create(email: str, password: str, role: Role) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with maker() as session:
            user = await register_user(session, email, password, role=role)
    except EmailAlreadyRegistered:
        raise SystemExit(f"이미 가입된 이메일입니다: {email}") from None
    finally:
        await engine.dispose()

    print(f"생성됨: {user.email} (id={user.id}, role={user.role})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="TCAD 계정을 만든다")
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--admin",
        action="store_true",
        help="관리자로 만든다. 동시 접속 정원과 유휴 만료를 면제받는다.",
    )
    arguments = parser.parse_args(argv)

    if not sys.stdin.isatty():
        # 파이프로 비밀번호를 넣으면 확인 절차가 무의미해진다.
        raise SystemExit("대화형 터미널에서 실행해 주세요")

    role = Role.ADMIN if arguments.admin else Role.USER
    asyncio.run(_create(arguments.email, _read_password(), role))


if __name__ == "__main__":
    main()
