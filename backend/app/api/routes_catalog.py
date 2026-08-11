"""커맨드 카탈로그 엔드포인트.

에디터의 자동완성·진단·문법 도움말이 여기에 물린다.

**인증을 요구하지 않는다.** 내용이 전부 레포에 들어 있는 오픈소스 정의 파일
(SUPREM4GS/data/suprem.key)에서 나오고 사용자 데이터가 섞이지 않는다. 로그인을
요구하면 로그인 화면에서 문법 도움말을 못 쓰고, 정적인 응답인데도 nginx 가
캐시할 수 없다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.catalog.catalog import Catalog, WordKind, load_catalog
from app.catalog.keywords import INTERPRETER_KEYWORDS
from app.catalog.models import Command, Parameter

router = APIRouter(prefix="/catalog", tags=["catalog"])


class ParameterResponse(BaseModel):
    name: str
    type: str
    source_name: str
    truncated: bool
    default: str | None
    units: str | None
    description: str | None
    error: str | None
    message: str | None
    group: str | None
    group_message: str | None
    unreachable: bool


class CommandSummary(BaseModel):
    name: str
    description: str | None
    parameter_count: int


class KeywordResponse(BaseModel):
    name: str
    description: str


class CommandListResponse(BaseModel):
    commands: list[CommandSummary]
    keywords: list[KeywordResponse]


class CommandDetail(BaseModel):
    name: str
    source_name: str
    description: str | None
    parameters: list[ParameterResponse]


class ResolveResponse(BaseModel):
    kind: str
    name: str | None
    candidates: list[str]


class Completion(BaseModel):
    name: str
    kind: str
    description: str | None


class CompletionResponse(BaseModel):
    completions: list[Completion]


def _catalog() -> Catalog:
    # lru_cache 라 프로세스당 한 번만 파싱한다. Depends 로 만들 만한 상태가 없다.
    return load_catalog()


@router.get("/commands")
async def index() -> CommandListResponse:
    """커맨드 목록.

    파라미터는 싣지 않는다. 1175개를 전부 담으면 응답이 300KB 를 넘는데, 목록
    화면에서는 쓰이지 않는다.
    """
    catalog = _catalog()
    return CommandListResponse(
        commands=[
            CommandSummary(
                name=command.name,
                description=command.description,
                parameter_count=len(command.parameters),
            )
            for command in catalog.commands
        ],
        keywords=[
            KeywordResponse(name=k.name, description=k.description)
            for k in INTERPRETER_KEYWORDS
        ],
    )


@router.get("/commands/{token}")
async def detail(token: str) -> CommandDetail:
    """커맨드 하나. 사용자가 친 그대로 넘어오므로 접두사로 해석한다."""
    command = _resolve_command_or_error(token)
    return CommandDetail(
        name=command.name,
        source_name=command.source_name,
        description=command.description,
        parameters=[_parameter(p) for p in command.parameters],
    )


@router.get("/resolve")
async def resolve_word(
    token: str = Query(min_length=1, max_length=64),
) -> ResolveResponse:
    """줄의 첫 단어가 무엇으로 해석되는지.

    `unknown` 이 중요하다. 인식되지 않는 첫 단어는 오류 없이 /bin/bash 로
    넘어가므로, 에디터가 경고하지 않으면 오타가 조용히 지나간다.
    """
    match = _catalog().resolve_word(token)
    return ResolveResponse(
        kind=match.kind.value,
        name=match.name,
        candidates=list(match.candidates),
    )


@router.get("/complete")
async def complete(
    prefix: str = Query(default="", max_length=64),
    command: str | None = Query(default=None, max_length=64),
) -> CompletionResponse:
    """자동완성 후보.

    `command` 를 주면 그 커맨드의 파라미터를, 주지 않으면 커맨드와 키워드를
    돌려준다.
    """
    catalog = _catalog()

    if command is not None:
        resolved = _resolve_command_or_error(command)
        return CompletionResponse(
            completions=[
                Completion(
                    name=parameter.name,
                    kind=parameter.type.value,
                    description=parameter.units or parameter.description,
                )
                for parameter in catalog.complete_parameters(resolved, prefix)
            ]
        )

    completions = [
        Completion(
            name=found.name, kind="command", description=found.description
        )
        for found in catalog.complete_commands(prefix)
    ]
    # 키워드는 접두사로 줄여 쓸 수 없지만, 후보로 보여 주는 것은 접두사 기준이
    # 맞다. 사용자는 이름 앞부분을 치고 있기 때문이다.
    completions += [
        Completion(name=k.name, kind="keyword", description=k.description)
        for k in INTERPRETER_KEYWORDS
        if k.name.startswith(prefix)
    ]
    return CompletionResponse(completions=completions)


def _resolve_command_or_error(token: str) -> Command:
    catalog = _catalog()
    match = catalog.resolve_word(token)

    if match.kind is WordKind.COMMAND:
        return catalog.get(match.name)

    if match.kind is WordKind.AMBIGUOUS:
        # 어디까지 더 쳐야 하는지 알려주려면 후보가 필요하다.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"{token!r} 은(는) 여러 커맨드에 걸립니다",
                "candidates": list(match.candidates),
            },
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{token!r} 에 해당하는 커맨드가 없습니다",
    )


def _parameter(parameter: Parameter) -> ParameterResponse:
    return ParameterResponse(
        name=parameter.name,
        type=parameter.type.value,
        source_name=parameter.source_name,
        truncated=parameter.truncated,
        default=parameter.default,
        units=parameter.units,
        description=parameter.description,
        error=parameter.error,
        message=parameter.message,
        group=parameter.group,
        group_message=parameter.group_message,
        unreachable=parameter.unreachable,
    )
