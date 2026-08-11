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

from pydantic import BaseModel, EmailStr, ValidationError

from app.auth.models import Role
from app.auth.service import EmailAlreadyRegistered, register_user
from app.core.config import get_settings

#: routes_auth 의 RegisterRequest 와 같은 하한. 두 경로가 어긋나면 CLI 로만
#: 약한 비밀번호를 심을 수 있게 된다.
_MIN_PASSWORD_LENGTH = 12


class _EmailCheck(BaseModel):
    """API 와 **같은** 검증기. 따로 만들면 두 경로가 어긋난다."""

    email: EmailStr


def validate_email(email: str) -> str:
    """API 가 받아들일 주소인지 확인한다.

    CLI 와 API 의 기준이 다르면 로그인할 수 없는 계정이 만들어진다. 실제로
    겪었다 — CLI 로 admin@tcad.local 을 만들었더니 계정은 생겼는데 로그인이
    422 로 거절됐다(.local 은 예약 도메인이다). 첫 관리자를 그렇게 만들면
    초대를 발급할 방법이 없어 서비스 전체가 막힌다.

    Raises:
        SystemExit: 쓸 수 없는 주소일 때.
    """
    try:
        return str(_EmailCheck(email=email).email)
    except ValidationError as error:
        reason = error.errors()[0].get("msg", "형식이 올바르지 않습니다")
        raise SystemExit(f"쓸 수 없는 이메일입니다: {email}\n  {reason}") from None


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

    # 이메일을 **가장 먼저** 확인한다. TTY 검사를 앞에 두면, 주소가 잘못됐을
    # 때 "대화형 터미널에서 실행해 주세요"라는 엉뚱한 메시지만 보게 된다.
    # 비밀번호를 다 치고 나서 거절당하지 않게 하는 효과도 있다.
    email = validate_email(arguments.email)

    if not sys.stdin.isatty():
        # 파이프로 비밀번호를 넣으면 확인 절차가 무의미해진다.
        raise SystemExit("대화형 터미널에서 실행해 주세요")

    role = Role.ADMIN if arguments.admin else Role.USER
    asyncio.run(_create(email, _read_password(), role))


if __name__ == "__main__":
    main()
