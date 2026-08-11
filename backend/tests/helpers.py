"""테스트 공용 도우미.

가입은 초대 코드를 요구한다. 그 요구를 테스트에서 끄는 설정을 두지 않는 것이
중요하다 — 끌 수 있게 만들면 배포에서 실수로 꺼질 수 있고, 그 순간 가입이
개방된다. 대신 테스트가 실제로 초대를 발급해서 쓴다.
"""

from __future__ import annotations

from app.auth.invites import issue_invite

PASSWORD = "correct-horse-battery-staple"


async def fresh_invite_code(sessionmaker) -> str:
    """쓸 수 있는 초대 코드 하나. 발급자는 없어도 된다(created_by 는 NULL 허용)."""
    async with sessionmaker() as session:
        _, code = await issue_invite(session, created_by=None)
    return code


async def register(client, sessionmaker, email: str, password: str = PASSWORD):
    """초대를 발급해 가입시킨다. 실제 가입 경로를 그대로 지난다."""
    return await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "invite_code": await fresh_invite_code(sessionmaker),
        },
    )


async def register_and_login(client, sessionmaker, email: str, password: str = PASSWORD):
    await register(client, sessionmaker, email, password)
    return await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
