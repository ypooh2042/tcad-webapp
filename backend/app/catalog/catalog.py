"""카탈로그 조회 표면.

`suprem.key` 는 82KB 고 파싱은 한 번이면 된다. 프로세스마다 한 번 읽어 캐시한다.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.catalog.key_parser import parse_key
from app.catalog.keywords import KEYWORD_NAMES
from app.catalog.models import Command, Parameter
from app.catalog.resolution import Match, Resolution, resolve


class WordKind(enum.Enum):
    """첫 단어가 무엇으로 해석되는지."""

    KEYWORD = "keyword"
    COMMAND = "command"
    AMBIGUOUS = "ambiguous"
    #: 어디에도 걸리지 않아 /bin/bash 로 넘어가는 경우.
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WordMatch:
    kind: WordKind
    name: str | None = None
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Catalog:
    commands: tuple[Command, ...]

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(command.name for command in self.commands)

    def get(self, name: str) -> Command | None:
        """이름이 정확히 일치하는 커맨드."""
        for command in self.commands:
            if command.name == name:
                return command
        return None

    def resolve_command(self, token: str) -> Match:
        return resolve(token, self.command_names)

    def lookup_command(self, token: str) -> tuple[Command | None, Match]:
        """접두사로 커맨드를 찾는다. 사용자가 친 그대로를 받는 입구다."""
        match = self.resolve_command(token)
        if match.status is not Resolution.RESOLVED:
            return None, match
        return self.get(match.name), match

    def resolve_word(self, token: str) -> WordMatch:
        """줄의 첫 단어를 시뮬레이터와 같은 순서로 판정한다.

        1. 인터프리터 키워드와 **정확히** 같으면 인터프리터가 가져간다.
           키워드에는 접두사 해석이 없다 — `sourc` 는 통하지 않는다.
        2. 아니면 카드 이름에 대해 **접두사** 해석을 한다.
        3. 그래도 안 되면 그 줄은 통째로 /bin/bash 로 넘어간다.

        두 공간은 서로 간섭하지 않는다. `set` 은 카드 select/selenium 이
        모호하든 말든 키워드로 처리된다.
        """
        if token in KEYWORD_NAMES:
            return WordMatch(WordKind.KEYWORD, name=token)

        match = self.resolve_command(token)
        if match.status is Resolution.RESOLVED:
            return WordMatch(WordKind.COMMAND, name=match.name)
        if match.status is Resolution.AMBIGUOUS:
            return WordMatch(WordKind.AMBIGUOUS, candidates=match.candidates)
        return WordMatch(WordKind.UNKNOWN)

    def resolve_parameter(self, command: Command, token: str) -> Match:
        return resolve(token, command.parameter_names)

    def complete_commands(self, prefix: str) -> tuple[Command, ...]:
        return tuple(
            command
            for command in self.commands
            if command.name.startswith(prefix)
        )

    def complete_parameters(
        self, command: Command, prefix: str
    ) -> tuple[Parameter, ...]:
        """자동완성 후보.

        지목 불가능한 파라미터는 내놓지 않는다. 골라 봐야 시뮬레이터가
        "ambiguous" 로 거절한다.
        """
        return tuple(
            parameter
            for parameter in command.parameters
            if parameter.name.startswith(prefix) and not parameter.unreachable
        )


#: 레포 안 SUPREM4GS 배포본. backend/app/catalog/catalog.py 기준으로 거슬러 올라간다.
_DEFAULT_KEY_PATH = (
    Path(__file__).resolve().parents[3] / "SUPREM4GS" / "data" / "suprem.key"
)


@lru_cache(maxsize=4)
def load_catalog(key_path: Path | None = None) -> Catalog:
    """suprem.key 를 읽어 카탈로그를 만든다. 프로세스당 한 번만 파싱한다."""
    path = key_path or _DEFAULT_KEY_PATH
    # 1993년 파일이라 순수 ASCII 가 아니다. 깨진 바이트 때문에 기동이 막히면
    # 안 되므로 대체 문자로 넘긴다.
    return Catalog(parse_key(path.read_text(errors="replace")))
