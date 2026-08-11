"""커맨드 카탈로그의 자료형.

카탈로그의 목적은 "SUPREM 이 실제로 받아들이는 것"을 알려주는 것이다. 문서에
적힌 이름과 런타임이 아는 이름이 다르면 런타임 쪽을 따른다.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

#: 런타임이 인식하는 이름의 최대 길이.
#:
#: 메타데이터는 suprem.key 에 있지만 시뮬레이터가 실행 중 읽는 파일은
#: suprem.uk 이고, 거기서는 이름이 이 길이로 잘려 저장된다. 해석이 접두사
#: 방식이라 잘린 이름보다 **긴** 토큰은 어디에도 걸리지 않는다. 즉 원형
#: 이름을 그대로 쓰면 거절된다.
#:
#: 실제 시뮬레이터로 확인했다(deposit 카드의 concentration):
#:     concentration (13자) → errors detected
#:     concentratio  (12자) → errors detected
#:     concentrati   (11자) → 정상
RUNTIME_NAME_LIMIT = 11


class ParameterType(enum.Enum):
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    BOOLEAN = "boolean"


def runtime_name(name: str) -> str:
    """suprem.key 의 이름을 런타임이 아는 형태로 바꾼다."""
    return name[:RUNTIME_NAME_LIMIT]


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    type: ParameterType
    #: suprem.key 에 적힌 원형. name 과 다를 수 있다(11자 초과 시). 문서에서
    #: 찾을 때 필요하므로 버리지 않는다.
    source_name: str
    default: str | None = None
    units: str | None = None
    description: str | None = None
    #: 값이 잘못됐을 때 시뮬레이터가 검사하는 조건식과 그때 내는 메시지.
    error: str | None = None
    message: str | None = None
    #: switch 묶음. 같은 group 안에서는 하나만 고를 수 있다.
    group: str | None = None
    group_message: str | None = None
    #: 다른 파라미터 이름의 진접두사라 어떤 입력으로도 지목할 수 없는 경우.
    #: SUPREM 에는 정확 일치 우선 규칙이 없어서 생기는 현상이다.
    unreachable: bool = False

    @property
    def truncated(self) -> bool:
        return self.name != self.source_name


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    source_name: str
    description: str | None = None
    parameters: tuple[Parameter, ...] = field(default_factory=tuple)

    @property
    def truncated(self) -> bool:
        return self.name != self.source_name

    @property
    def parameter_names(self) -> tuple[str, ...]:
        return tuple(parameter.name for parameter in self.parameters)

    def parameter(self, name: str) -> Parameter | None:
        """이름이 정확히 일치하는 파라미터. 접두사 해석은 resolution 이 한다."""
        for parameter in self.parameters:
            if parameter.name == name:
                return parameter
        return None
