"""비밀번호 해싱 테스트."""

import pytest

from app.auth.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
)


class TestHashing:
    def test_hash_is_not_the_plaintext(self) -> None:
        assert hash_password("correct horse battery staple") != (
            "correct horse battery staple"
        )

    def test_uses_argon2(self) -> None:
        assert hash_password("pw").startswith("$argon2")

    def test_same_password_hashes_differently(self) -> None:
        """솔트가 매번 달라야 레인보우 테이블과 해시 비교 공격을 막는다."""
        assert hash_password("same") != hash_password("same")

    def test_rejects_empty_password(self) -> None:
        with pytest.raises(ValueError, match="비어"):
            hash_password("")


class TestVerification:
    def test_accepts_correct_password(self) -> None:
        assert verify_password(hash_password("s3cret"), "s3cret")

    def test_rejects_wrong_password(self) -> None:
        assert not verify_password(hash_password("s3cret"), "wrong")

    def test_rejects_empty_attempt(self) -> None:
        assert not verify_password(hash_password("s3cret"), "")

    def test_malformed_hash_fails_closed(self) -> None:
        """저장된 해시가 깨져 있으면 인증 실패로 처리한다(통과시키지 않는다)."""
        assert not verify_password("not-a-hash", "anything")

    def test_unicode_password_roundtrips(self) -> None:
        password = "비밀번호12!@가나다"
        assert verify_password(hash_password(password), password)

    def test_long_password_is_supported(self) -> None:
        password = "x" * 1024
        assert verify_password(hash_password(password), password)


class TestRehash:
    def test_current_hash_does_not_need_rehash(self) -> None:
        assert not needs_rehash(hash_password("pw"))

    def test_weaker_legacy_hash_needs_rehash(self) -> None:
        """파라미터가 약한 예전 해시는 로그인 성공 시 갱신 대상이다."""
        weak = (
            "$argon2id$v=19$m=8,t=1,p=1$"
            "c29tZXNhbHRzYWx0$JPFCLLCoRHUVBjIsz9pZ0lNJmZ2bqBiRZ0N0kCUFmEo"
        )
        assert needs_rehash(weak)

    def test_malformed_hash_is_treated_as_needing_rehash(self) -> None:
        assert needs_rehash("garbage")
