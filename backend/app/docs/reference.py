"""커맨드 레퍼런스 — 무엇을 찾아야 할지 모를 때 보는 목록.

검색(app/docs/manual.py)과 역할이 다르다. 검색은 찾는 낱말을 알 때 쓴다.
처음 쓰는 사람은 그 낱말을 모른다 — "층을 쌓는 커맨드가 뭐지" 를 검색으로
알아낼 수는 없다. 그래서 무리별로 훑어볼 수 있는 목록이 따로 필요하다.

**분류는 매뉴얼이 정한 것을 그대로 쓴다.** 매뉴얼 p.51 이 커맨드를 네 무리로
나눠 설명하고 있어서, 임의로 다시 묶으면 매뉴얼과 대조할 수 없다.

데이터는 tools/docs/build_reference.py 가 만든다(매뉴얼 PDF + suprem.key).
추출에 pdftotext 가 필요하므로 배포 때가 아니라 개발 때 한 번 돌리고 결과를
레포에 넣는다 — manual.json 과 같은 방식이다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent / "data" / "reference.json"


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    type: str
    default: str | None
    units: str | None
    group: str | None
    #: 매뉴얼에 인쇄된 이름. 11자를 넘으면 name 과 다르다.
    source_name: str
    #: 런타임이 11자로 잘라서 인식하는가. 매뉴얼대로 치면 안 먹힌다.
    truncated: bool
    #: 접두사 해석으로 도달할 수 없는가(더 짧은 이름에 가려진다).
    unreachable: bool


@dataclass(frozen=True, slots=True)
class Command:
    #: 매뉴얼에 인쇄된 이름. 사람이 읽고 그대로 쳐도 통과한다.
    name: str
    #: 런타임이 인식하는 이름(11자 상한). 전체 이름을 쳐도 앞 11자로 비교되므로
    #: 실사용에는 차이가 없다 — 파라미터와 달리 경고할 필요가 없다.
    runtime_name: str
    group: str
    #: 매뉴얼의 한 줄 요약. 목록에서 이것만 보고 고른다.
    summary: str
    #: 매뉴얼에 설명이 있는가. suprem.key 에만 있는 커맨드는 False.
    documented: bool
    synopsis: str
    manual_page: str | None
    #: 본문을 읽을 때 쓸 섹션 id. 문서가 없으면 None.
    manual_section_id: str | None
    parameters: tuple[Parameter, ...]


@dataclass(frozen=True, slots=True)
class Group:
    name: str
    #: 이 무리가 무엇인지. 이름만으로는 왜 묶였는지 알 수 없다.
    note: str
    commands: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Reference:
    groups: tuple[Group, ...]
    commands: tuple[Command, ...]

    def get(self, name: str) -> Command:
        """커맨드 이름으로 조회한다.

        Raises:
            KeyError: 없는 이름일 때.
        """
        for command in self.commands:
            if command.name == name:
                return command
        raise KeyError(name)


@lru_cache(maxsize=1)
def load_reference(path: Path | None = None) -> Reference:
    """레퍼런스를 읽는다. 프로세스당 한 번만 파싱한다(800KB)."""
    raw = json.loads((path or _DATA_PATH).read_text())
    return Reference(
        groups=tuple(
            Group(
                name=group["name"],
                note=group["note"],
                commands=tuple(group["commands"]),
            )
            for group in raw["groups"]
        ),
        commands=tuple(
            Command(
                name=command["name"],
                runtime_name=command["runtime_name"],
                group=command["group"],
                summary=command["summary"],
                documented=command["documented"],
                synopsis=command["synopsis"],
                manual_page=command["manual_page"],
                manual_section_id=command["manual_section_id"],
                parameters=tuple(
                    Parameter(
                        name=parameter["name"],
                        type=parameter["type"],
                        default=parameter["default"],
                        units=parameter["units"],
                        group=parameter["group"],
                        source_name=parameter["source_name"],
                        truncated=parameter["truncated"],
                        unreachable=parameter["unreachable"],
                    )
                    for parameter in command["parameters"]
                ),
            )
            for command in raw["commands"]
        ),
    )
