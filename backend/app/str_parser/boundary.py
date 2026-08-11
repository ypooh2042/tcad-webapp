"""경계 조건 sentinel.

`t` 라인의 이웃 필드가 음수이면 이웃 요소가 아니라 경계 조건 코드다.
suprem 바이너리의 `ChosenBC()` 가 `"/reflect"`, `"/backside"`, `"/exposed"`
문자열 테이블에서 i번째로 일치한 항목에 대해 `-1024 + i` 를 반환한다.
"""

from __future__ import annotations

from enum import Enum


class BoundaryCondition(Enum):
    """메시 바깥 경계의 종류."""

    REFLECT = -1024
    BACKSIDE = -1023
    EXPOSED = -1022
    UNDEFINED = -1025
    #: 위 어느 코드에도 없는 음수. 임의로 해석하지 않고 모른다고 표시한다.
    UNKNOWN = 0

    @classmethod
    def resolve(cls, code: int) -> BoundaryCondition:
        try:
            return cls(code)
        except ValueError:
            return cls.UNKNOWN
