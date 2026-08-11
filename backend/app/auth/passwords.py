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

#: 일반 사용자 비밀번호 최소 길이.
#:
#: 6자가 그 자체로 안전해서가 아니라 이 서비스의 조건에서 받아들일 만해서다:
#: 가입이 초대제라 아무나 계정을 만들 수 없고, 로그인 시도가 계정당 15분에
#: 10회로 묶여 있어 온라인 대입이 사실상 불가능하며, argon2id 로 저장한다.
#:
#: 남는 위험은 DB 가 통째로 유출됐을 때의 오프라인 대입이다. 6자는 그 상황에서
#: 길지 않다 — 그때는 전원 비밀번호 재설정이 필요하다.
MIN_PASSWORD_LENGTH = 6

#: 관리자 비밀번호 최소 길이.
#:
#: 관리자는 초대를 발급할 수 있고 동시 접속 정원과 유휴 만료를 면제받는다.
#: 그 계정이 뚫리면 서비스 전체가 열리므로 기준을 따로 둔다.
MIN_ADMIN_PASSWORD_LENGTH = 12


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
