"""비밀번호 길이 정책.

일반 사용자는 6자, 관리자는 12자다. 기준을 나눈 이유는 두 계정이 지는 위험이
다르기 때문이다 — 관리자는 초대를 발급할 수 있고 동시 접속 정원과 유휴 만료를
면제받는다. 그 계정이 뚫리면 서비스 전체가 열린다.

6자가 안전해서가 아니라 이 서비스의 조건에서 받아들일 만해서다:
  - 가입이 초대제라 아무나 계정을 만들 수 없다
  - 로그인 시도가 계정당 15분에 10회로 묶여 있어 온라인 대입은 사실상 불가능
  - 비밀번호는 argon2id 로 저장한다

남는 위험은 **DB 가 통째로 유출됐을 때**의 오프라인 대입이다. 6자는 그 상황에서
길지 않다. 그때는 전원 비밀번호 재설정이 필요하다.
"""

from __future__ import annotations

import pytest

from app.auth.passwords import (
    MIN_ADMIN_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
)


class TestPolicyValues:
    def test_regular_users_need_six(self) -> None:
        assert MIN_PASSWORD_LENGTH == 6

    def test_admins_need_more(self) -> None:
        """관리자가 뚫리면 초대를 무제한으로 찍어낼 수 있다."""
        assert MIN_ADMIN_PASSWORD_LENGTH > MIN_PASSWORD_LENGTH
        assert MIN_ADMIN_PASSWORD_LENGTH == 12


class TestSingleSourceOfTruth:
    """세 곳(API·CLI·화면)이 각자 숫자를 들고 있으면 반드시 어긋난다."""

    def test_api_uses_the_constant(self) -> None:
        from app.api.routes_auth import RegisterRequest

        field = RegisterRequest.model_fields["password"]
        constraints = [
            getattr(meta, "min_length", None) for meta in field.metadata
        ]

        assert MIN_PASSWORD_LENGTH in constraints

    def test_cli_uses_the_admin_constant(self) -> None:
        from app.auth import create_user

        assert create_user._MIN_ADMIN_PASSWORD_LENGTH == MIN_ADMIN_PASSWORD_LENGTH

    def test_frontend_matches(self) -> None:
        """화면이 더 느슨하면 사용자가 입력하고 나서 서버에 거절당한다."""
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3]
            / "frontend/src/features/auth/LoginPage.tsx"
        ).read_text()

        assert f"minLength={{{MIN_PASSWORD_LENGTH}}}" in source
