"""계정 생성 CLI 의 이메일 검증.

CLI 와 API 가 서로 다른 기준을 쓰면, **로그인할 수 없는 계정**이 만들어진다.
실제로 겪었다: CLI 로 admin@tcad.local 을 만들었더니 계정은 생겼는데 로그인이
422 로 거절됐다(.local 은 예약 도메인이라 email-validator 가 막는다). 첫
관리자를 그렇게 만들면 초대를 발급할 방법이 없어 서비스 전체가 막힌다.
"""

from __future__ import annotations

import pytest

from app.auth.create_user import validate_email


class TestEmailValidation:
    @pytest.mark.parametrize(
        "email",
        ["a@example.com", "user.name+tag@lab.ac.kr", "x@sub.domain.org"],
    )
    def test_accepts_real_addresses(self, email) -> None:
        assert validate_email(email)

    @pytest.mark.parametrize(
        "email",
        [
            "admin@tcad.local",   # 예약 도메인
            "admin@localhost",    # 예약 도메인
            "no-at-sign",
            "@example.com",
            "a@",
        ],
    )
    def test_rejects_what_the_api_would_reject(self, email) -> None:
        """API 가 거절할 주소는 CLI 도 거절해야 한다."""
        with pytest.raises(SystemExit):
            validate_email(email)

    def test_matches_the_api_validator(self) -> None:
        """같은 검증기를 써야 두 경로가 어긋나지 않는다."""
        from pydantic import BaseModel, EmailStr, ValidationError

        class ApiModel(BaseModel):
            email: EmailStr

        for email in ["admin@tcad.local", "a@example.com"]:
            api_ok = True
            try:
                ApiModel(email=email)
            except ValidationError:
                api_ok = False

            cli_ok = True
            try:
                validate_email(email)
            except SystemExit:
                cli_ok = False

            assert api_ok == cli_ok, email
