"""비밀번호 해싱.

argon2id 를 쓴다. 파라미터는 argon2-cffi 기본값을 따르되, 실패는 항상 "인증 실패"
쪽으로 닫는다. 해시가 깨졌을 때 예외가 위로 새어나가면 호출부가 그것을 성공으로
오인하거나 500 으로 사용자 존재 여부를 흘릴 수 있다.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHash,
    VerificationError,
    VerifyMismatchError,
)

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """비밀번호를 argon2id 해시로 만든다.

    Raises:
        ValueError: 빈 비밀번호. 빈 값이 해시되어 저장되면 빈 입력으로 로그인이
            된다. 상위 검증과 별개로 여기서도 막는다.
    """
    if not password:
        raise ValueError("비밀번호가 비어 있습니다")
    return _hasher.hash(password)


def verify_password(stored_hash: str, attempt: str) -> bool:
    """비밀번호를 검증한다. 어떤 이유로든 확신할 수 없으면 False."""
    if not attempt:
        return False
    try:
        return _hasher.verify(stored_hash, attempt)
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """저장된 해시가 현재 파라미터보다 약한지.

    로그인에 성공한 시점에만 호출해서(평문을 아는 유일한 시점) 새 해시로
    갱신한다. 해시를 읽을 수 없으면 갱신 대상으로 본다.
    """
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHash:
        return True
