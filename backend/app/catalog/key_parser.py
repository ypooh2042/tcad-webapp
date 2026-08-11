"""`suprem.key` 파서.

문법은 파일 헤더와 파일 자체에서 유도했다:

    file    := stmt*
    stmt    := decl ';' [ '{' stmt* '}' ]
    decl    := TYPE NAME [ '=' DEFAULT ]
               [ 'units' '=' STRING ] [ 'message' '=' STRING ]
               [ 'error' '=' EXPR ]                      (절 순서는 자유)
    comment := '#' .. 줄 끝

`switch` 는 상호배타 선택지의 묶음이고 선택지들은 뒤따르는 `{}` 안에 있다.
`boolean` 도 블록을 가질 수 있다(structure mirror → right/left/top/bottom).

메타데이터는 이 파일에만 있다. 시뮬레이터가 실행 중 읽는 suprem.uk 는 이름과
기본값만 담은 바이너리라 설명·단위·오류 조건을 얻을 수 없다. 대신 이름은
suprem.uk 쪽이 진실이므로 여기서 읽은 이름은 런타임 길이로 자른다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.catalog.models import (
    Command,
    Parameter,
    ParameterType,
    runtime_name,
)
from app.catalog.resolution import is_unreachable

_TYPES = {"card", "int", "integer", "float", "string", "boolean", "switch"}
_CLAUSES = {"units", "message", "error"}

#: int 는 integer 의 별칭이다.
_TYPE_ALIASES = {"int": "integer"}

_TOKEN_RE = re.compile(
    r"""
      (?P<comment>\#[^\n]*)
    | (?P<string>"(?:[^"\\]|\\.)*")
    | (?P<punct>[{};=])
    | (?P<ws>\s+)
    | (?P<name>[A-Za-z_/][A-Za-z0-9_./]*)
    | (?P<number>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
    | (?P<other>\S)
    """,
    re.VERBOSE,
)

#: "card 12" 처럼 번호만 적힌 주석은 설명이 아니라 색인이다.
_CARD_INDEX_RE = re.compile(r"card\s+\d+")


class KeyFormatError(Exception):
    """suprem.key 를 읽을 수 없을 때."""


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    line: int


@dataclass(slots=True)
class _Node:
    """파싱 중간 표현. 트리를 다 만든 뒤 Command/Parameter 로 옮긴다."""

    type: str
    name: str
    line: int
    default: str | None = None
    units: str | None = None
    message: str | None = None
    error: str | None = None
    description: str | None = None
    children: list[_Node] | None = None


def parse_key(text: str) -> tuple[Command, ...]:
    """suprem.key 내용을 커맨드 목록으로 바꾼다."""
    nodes = _Parser(_tokenize(text)).parse()
    return tuple(
        _build_command(node) for node in nodes if node.type == "card"
    )


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    line = 1
    position = 0
    while position < len(text):
        match = _TOKEN_RE.match(text, position)
        if match is None:
            raise KeyFormatError(
                f"{line}번 줄을 토큰으로 나눌 수 없습니다: "
                f"{text[position:position + 40]!r}"
            )
        kind = match.lastgroup
        value = match.group()
        if kind != "ws":
            # 주석은 버리지 않는다. 파라미터 설명의 유일한 출처다.
            tokens.append(_Token(kind, value, line))
        line += value.count("\n")
        position = match.end()
    return tokens


def _clean_comment(text: str) -> str:
    return text.lstrip("#").lstrip("!").strip()


class _Parser:
    """재귀 하강 파서."""

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._index = 0

    def parse(self) -> list[_Node]:
        return self._parse_block()

    @property
    def _current(self) -> _Token:
        return self._tokens[self._index]

    @property
    def _at_end(self) -> bool:
        return self._index >= len(self._tokens)

    def _parse_block(self) -> list[_Node]:
        nodes: list[_Node] = []
        pending: list[tuple[int, str]] = []  # 아직 선언에 붙지 않은 주석들

        while not self._at_end:
            token = self._current

            if token.kind == "comment":
                pending.append((token.line, _clean_comment(token.value)))
                self._index += 1
                continue

            if token.kind == "name" and token.value == "end":
                # 파일 마지막 줄의 종료 표시.
                self._index += 1
                continue

            if token.kind == "punct" and token.value == "}":
                self._index += 1
                return nodes

            if token.kind == "punct" and token.value == "{":
                # 바로 앞 선언에 딸린 블록.
                self._index += 1
                children = self._parse_block()
                if nodes:
                    node = nodes[-1]
                    node.children = (node.children or []) + children
                else:
                    nodes.extend(children)
                pending = []
                continue

            node, trailing = self._parse_declaration()
            node.description = _build_description(pending, node.line, trailing)
            nodes.append(node)
            pending = []

        return nodes

    def _parse_declaration(self) -> tuple[_Node, str | None]:
        token = self._current
        if token.kind != "name" or token.value not in _TYPES:
            raise KeyFormatError(
                f"{token.line}번 줄: 타입 키워드가 와야 하는데 {token.value!r}"
            )
        node_type = token.value
        line = token.line
        self._index += 1

        if self._current.kind != "name":
            raise KeyFormatError(f"{line}번 줄: {node_type!r} 뒤에 이름이 없습니다")
        node = _Node(type=node_type, name=self._current.value, line=line)
        self._index += 1

        # 이름 바로 뒤의 '=' 는 기본값이다.
        if self._current.kind == "punct" and self._current.value == "=":
            self._index += 1
            node.default = self._current.value.strip('"')
            self._index += 1

        self._parse_clauses(node)
        return node, self._take_trailing_comment()

    def _parse_clauses(self, node: _Node) -> None:
        while not (self._current.kind == "punct" and self._current.value == ";"):
            token = self._current

            if token.kind == "comment":
                self._index += 1
                continue

            if token.kind != "name" or token.value not in _CLAUSES:
                raise KeyFormatError(
                    f"{token.line}번 줄: 선언 안에 예상 밖의 토큰 {token.value!r}"
                )

            clause = token.value
            self._index += 1
            if self._current.value != "=":
                raise KeyFormatError(f"{token.line}번 줄: {clause!r} 뒤에 '=' 필요")
            self._index += 1

            if clause == "error":
                node.error = self._parse_expression()
            else:
                setattr(node, clause, self._current.value.strip('"'))
                self._index += 1

    def _parse_expression(self) -> str:
        """error 절은 임의의 조건식이라 ';' 까지 그대로 모은다."""
        parts: list[str] = []
        while not (self._current.kind == "punct" and self._current.value == ";"):
            if self._current.kind == "comment":
                self._index += 1
                continue
            parts.append(self._current.value)
            self._index += 1
        return " ".join(parts)

    def _take_trailing_comment(self) -> str | None:
        """';' 를 소비하고, 같은 줄에 이어지는 주석이 있으면 돌려준다."""
        semicolon_line = self._current.line
        self._index += 1
        if (
            not self._at_end
            and self._current.kind == "comment"
            and self._current.line == semicolon_line
        ):
            comment = _clean_comment(self._current.value)
            self._index += 1
            return comment
        return None


def _build_description(
    pending: list[tuple[int, str]], declaration_line: int, trailing: str | None
) -> str | None:
    """선언 바로 위에 붙어 있는 주석 블록 + 같은 줄 주석.

    떨어져 있는 주석은 다른 선언의 설명이거나 구획 표시라 가져오면 안 된다.
    """
    block: list[tuple[int, str]] = []
    previous: int | None = None
    for line, text in pending:
        if previous is not None and line != previous + 1:
            block = []  # 끊겼으면 처음부터 다시
        block.append((line, text))
        previous = line

    if block and block[-1][0] != declaration_line - 1:
        block = []  # 선언에 붙어 있지 않다

    parts = [
        text
        for _, text in block
        if text and not _CARD_INDEX_RE.fullmatch(text)
    ]
    if trailing:
        parts.append(trailing)
    return " ".join(parts).strip() or None


def _build_command(node: _Node) -> Command:
    parameters = _flatten(node.children or [])
    names = [parameter.name for parameter in parameters]
    return Command(
        name=runtime_name(node.name),
        source_name=node.name,
        description=node.description,
        parameters=tuple(
            _with_reachability(parameter, names) for parameter in parameters
        ),
    )


def _with_reachability(parameter: Parameter, names: list[str]) -> Parameter:
    if not is_unreachable(parameter.name, names):
        return parameter
    # frozen dataclass 라 새로 만든다.
    return Parameter(
        name=parameter.name,
        type=parameter.type,
        source_name=parameter.source_name,
        default=parameter.default,
        units=parameter.units,
        description=parameter.description,
        error=parameter.error,
        message=parameter.message,
        group=parameter.group,
        group_message=parameter.group_message,
        unreachable=True,
    )


def _flatten(
    nodes: list[_Node],
    group: _Node | None = None,
    into: list[Parameter] | None = None,
) -> list[Parameter]:
    """카드 아래 트리를 평평한 파라미터 목록으로 편다.

    switch 는 파라미터가 아니라 상호배타 묶음이므로 자기 자신은 목록에 넣지
    않고, 자식들에게 묶음 이름만 붙여 내려보낸다.
    """
    result = [] if into is None else into

    for node in nodes:
        if node.type == "switch":
            _flatten(node.children or [], node, result)
            continue

        result.append(
            Parameter(
                name=runtime_name(node.name),
                type=ParameterType(_TYPE_ALIASES.get(node.type, node.type)),
                source_name=node.name,
                default=node.default,
                units=node.units,
                description=node.description,
                error=node.error,
                message=node.message,
                group=group.name if group else None,
                group_message=group.message if group else None,
            )
        )
        if node.children:
            # boolean 이 하위 선택지를 갖는 경우. 묶음은 그대로 물려받는다.
            _flatten(node.children, group, result)

    return result
