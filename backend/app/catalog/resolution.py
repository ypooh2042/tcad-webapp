"""SUPREM 의 이름 해석 규칙.

토큰이 어떤 이름의 접두사이면 그 이름으로 본다. 후보가 정확히 하나일 때만
통과하고, 둘 이상이면 "ambiguous" 로 거절된다.

주의할 점 두 가지가 있고, 둘 다 실제 시뮬레이터에 넣어 확인했다.

**정확 일치 우선 규칙이 없다.**
`backside` 는 structure 카드에 실재하는 파라미터인데도 `backside.y` 때문에
"ambiguous parameter - backside" 로 거절된다. 다른 이름의 진접두사인 이름은
어떤 입력으로도 지목할 수 없다. 여기서 정확 일치를 우선시키면 카탈로그가
시뮬레이터와 다르게 동작하게 되므로, 규칙을 그대로 옮긴다.

**대소문자를 구분한다.**
`STRUCTURE` 는 커맨드로 인식되지 않는다. 게다가 인식되지 않은 첫 단어는
/bin/bash 로 넘어가기 때문에 오류 메시지조차 나오지 않는다.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass


class Resolution(enum.Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Match:
    status: Resolution
    #: RESOLVED 일 때만 채워진다.
    name: str | None = None
    #: AMBIGUOUS 일 때의 후보들. 사용자가 어디까지 더 쳐야 하는지 알려면 필요하다.
    candidates: tuple[str, ...] = ()


def resolve(token: str, names: Iterable[str]) -> Match:
    """토큰을 이름 하나로 해석한다."""
    matches = tuple(name for name in names if name.startswith(token))

    if not matches:
        return Match(Resolution.UNKNOWN)
    if len(matches) == 1:
        return Match(Resolution.RESOLVED, name=matches[0])
    return Match(Resolution.AMBIGUOUS, candidates=matches)


def is_unreachable(name: str, names: Iterable[str]) -> bool:
    """이 이름이 다른 이름의 진접두사라 지목 불가능한지."""
    return any(other != name and other.startswith(name) for other in names)
