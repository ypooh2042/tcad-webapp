"""초대 코드.

가입을 열어 두면 도메인을 찾은 누구나 홈서버 컨테이너 안에서 코드를 실행할 수
있다. 격리는 별개로 튼튼하지만, 모르는 사람이 서버 자원을 쓰는 것 자체를 막아야
한다.

**코드는 argon2 로 저장하지 않는다.** argon2 는 솔트가 섞여 있어 해시로 행을
찾을 수 없고, 모든 초대를 하나씩 검증해야 한다 — 느릴 뿐 아니라 그 자체가
DoS 벡터다. 초대 코드는 비밀번호와 달리 256비트 무작위라 느린 해시가 필요 없다.
SHA-256 + 유니크 인덱스로 한 번에 찾는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.invites import (
    InviteExhausted,
    InviteExpired,
    InviteNotFound,
    InviteRevoked,
    issue_invite,
    redeem_invite,
    revoke_invite,
)
from app.db.models import Base, InviteCode, User


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as session:
        user = User(email="admin@example.com", password_hash="x", role="admin")
        session.add(user)
        await session.commit()
        return user.id


class TestIssuing:
    async def test_returns_the_code_once(self, session_factory, admin) -> None:
        """평문은 발급 순간에만 존재한다. DB 에는 해시만 남는다."""
        async with session_factory() as session:
            invite, code = await issue_invite(session, created_by=admin)

        assert code
        assert invite.code_hash != code

    async def test_code_is_high_entropy(self, session_factory, admin) -> None:
        async with session_factory() as session:
            _, first = await issue_invite(session, created_by=admin)
            _, second = await issue_invite(session, created_by=admin)

        assert first != second
        assert len(first) >= 32

    async def test_defaults_to_single_use(self, session_factory, admin) -> None:
        async with session_factory() as session:
            invite, _ = await issue_invite(session, created_by=admin)

        assert invite.max_uses == 1
        assert invite.used_count == 0

    async def test_defaults_to_seven_days(self, session_factory, admin) -> None:
        async with session_factory() as session:
            invite, _ = await issue_invite(session, created_by=admin)

        remaining = invite.expires_at - datetime.now(timezone.utc)
        assert timedelta(days=6) < remaining <= timedelta(days=7)

    async def test_accepts_custom_limits(self, session_factory, admin) -> None:
        async with session_factory() as session:
            invite, _ = await issue_invite(
                session, created_by=admin, max_uses=5, valid_for=timedelta(hours=1)
            )

        assert invite.max_uses == 5
        assert invite.expires_at - datetime.now(timezone.utc) <= timedelta(hours=1)

    async def test_records_the_issuer(self, session_factory, admin) -> None:
        """누가 발급했는지 남아야 나중에 계정 출처를 따질 수 있다."""
        async with session_factory() as session:
            invite, _ = await issue_invite(session, created_by=admin)

        assert invite.created_by == admin


class TestRedeeming:
    async def test_valid_code_is_accepted(self, session_factory, admin) -> None:
        async with session_factory() as session:
            _, code = await issue_invite(session, created_by=admin)

        async with session_factory() as session:
            invite = await redeem_invite(session, code)

        assert invite.used_count == 1

    async def test_unknown_code_is_rejected(self, session_factory) -> None:
        async with session_factory() as session:
            with pytest.raises(InviteNotFound):
                await redeem_invite(session, "존재하지-않는-코드")

    async def test_single_use_code_cannot_be_reused(
        self, session_factory, admin
    ) -> None:
        async with session_factory() as session:
            _, code = await issue_invite(session, created_by=admin)

        async with session_factory() as session:
            await redeem_invite(session, code)

        async with session_factory() as session:
            with pytest.raises(InviteExhausted):
                await redeem_invite(session, code)

    async def test_multi_use_code_works_until_exhausted(
        self, session_factory, admin
    ) -> None:
        async with session_factory() as session:
            _, code = await issue_invite(session, created_by=admin, max_uses=2)

        for _ in range(2):
            async with session_factory() as session:
                await redeem_invite(session, code)

        async with session_factory() as session:
            with pytest.raises(InviteExhausted):
                await redeem_invite(session, code)

    async def test_expired_code_is_rejected(self, session_factory, admin) -> None:
        async with session_factory() as session:
            _, code = await issue_invite(
                session, created_by=admin, valid_for=timedelta(seconds=-1)
            )

        async with session_factory() as session:
            with pytest.raises(InviteExpired):
                await redeem_invite(session, code)

    async def test_revoked_code_is_rejected(self, session_factory, admin) -> None:
        """회수는 재배포 없이 즉시 들어야 한다."""
        async with session_factory() as session:
            invite, code = await issue_invite(session, created_by=admin)
            invite_id = invite.id

        async with session_factory() as session:
            await revoke_invite(session, invite_id)

        async with session_factory() as session:
            with pytest.raises(InviteRevoked):
                await redeem_invite(session, code)

    async def test_concurrent_redemption_respects_the_limit(
        self, session_factory, admin
    ) -> None:
        """두 사람이 동시에 1회용 코드를 써도 한 명만 통과해야 한다.

        읽고 나서 쓰면 둘 다 used_count=0 을 보고 둘 다 통과한다. 조건부
        UPDATE 한 번으로 끝내야 한다.
        """
        async with session_factory() as session:
            invite, code = await issue_invite(session, created_by=admin)
            invite_id = invite.id

        # 두 세션이 같은 코드를 노린다.
        async with session_factory() as first, session_factory() as second:
            await redeem_invite(first, code)
            with pytest.raises(InviteExhausted):
                await redeem_invite(second, code)

        async with session_factory() as session:
            assert (await session.get(InviteCode, invite_id)).used_count == 1


class TestStorage:
    async def test_plaintext_is_never_stored(self, session_factory, admin) -> None:
        async with session_factory() as session:
            _, code = await issue_invite(session, created_by=admin)

        async with session_factory() as session:
            invite = await session.get(InviteCode, 1)

        assert code not in invite.code_hash

    async def test_hash_is_deterministic_for_lookup(
        self, session_factory, admin
    ) -> None:
        """같은 코드는 항상 같은 해시여야 인덱스로 한 번에 찾는다.

        argon2 처럼 솔트가 섞이면 모든 행을 하나씩 검증해야 한다.
        """
        from app.auth.invites import hash_code

        assert hash_code("abc") == hash_code("abc")
        assert hash_code("abc") != hash_code("abd")
