"""매뉴얼 엔드포인트.

카탈로그와 같은 이유로 인증을 요구하지 않는다 — 1993년 Stanford/UF 매뉴얼에서
나온 공개 자료이고 사용자 데이터가 섞이지 않는다. 로그인 화면에서도 문법을
찾아볼 수 있고 nginx 가 캐시할 수 있다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.docs.manual import Manual, Section, load_manual
from app.docs.reference import load_reference

router = APIRouter(prefix="/docs", tags=["docs"])


class ReferenceCommand(BaseModel):
    """목록에서 고르는 데 필요한 것만. 산문과 파라미터는 싣지 않는다 —
    전부 실으면 800KB 라, 패널을 여는 것만으로 그만큼을 받는다."""

    name: str
    summary: str
    documented: bool
    parameter_count: int
    #: 본문을 읽을 때 쓸 id. 매뉴얼에 설명이 없으면 None.
    manual_section_id: str | None
    manual_page: str | None


class ReferenceGroup(BaseModel):
    name: str
    note: str
    commands: list[ReferenceCommand]


class ReferenceResponse(BaseModel):
    groups: list[ReferenceGroup]


class SectionSummary(BaseModel):
    id: str
    kind: str
    title: str
    command: str | None
    page_start: str


class SectionDetail(SectionSummary):
    aliases: list[str]
    page_end: str
    pdf_page_start: int
    pdf_page_end: int
    subsections: dict[str, str]
    key_parameters: list[str]


class SearchHitResponse(BaseModel):
    id: str
    title: str
    command: str | None
    kind: str
    snippet: str


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHitResponse]


def _manual() -> Manual:
    # lru_cache 라 프로세스당 한 번만 읽는다.
    return load_manual()


def _summary(section: Section) -> SectionSummary:
    return SectionSummary(
        id=section.id,
        kind=section.kind,
        title=section.title,
        command=section.command,
        page_start=section.page_start,
    )


@router.get("/reference")
async def reference() -> ReferenceResponse:
    """커맨드 목록 — 무엇을 찾아야 할지 모를 때 훑어보는 것.

    검색과 역할이 다르다. 검색은 찾을 낱말을 알아야 쓸 수 있는데, 처음 쓰는
    사람은 그 낱말을 모른다. 무리별로 늘어놓아야 "층을 쌓는 커맨드" 를 눈으로
    찾을 수 있다.

    분류는 매뉴얼 p.51 이 나눈 것을 그대로 쓴다.
    """
    catalogue = load_reference()
    by_name = {command.name: command for command in catalogue.commands}

    return ReferenceResponse(
        groups=[
            ReferenceGroup(
                name=group.name,
                note=group.note,
                commands=[
                    ReferenceCommand(
                        name=command.name,
                        summary=command.summary,
                        documented=command.documented,
                        parameter_count=len(command.parameters),
                        manual_section_id=command.manual_section_id,
                        manual_page=command.manual_page,
                    )
                    for command in (by_name[name] for name in group.commands)
                ],
            )
            for group in catalogue.groups
        ]
    )


@router.get("/sections")
async def index(
    kind: str | None = Query(default=None, max_length=32),
) -> list[SectionSummary]:
    """섹션 목록. 본문은 싣지 않는다(전부 합치면 332KB 다)."""
    sections = _manual().sections
    if kind is not None:
        sections = tuple(s for s in sections if s.kind == kind)
    return [_summary(s) for s in sections]


@router.get("/sections/{section_id}")
async def detail(section_id: str) -> SectionDetail:
    try:
        section = _manual().get(section_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{section_id!r} 섹션이 없습니다",
        ) from None

    return SectionDetail(
        **_summary(section).model_dump(),
        aliases=list(section.aliases),
        page_end=section.page_end,
        pdf_page_start=section.pdf_page_start,
        pdf_page_end=section.pdf_page_end,
        subsections=section.subsections,
        key_parameters=list(section.key_parameters),
    )


@router.get("/for-command/{token}")
async def for_command(token: str) -> SectionDetail:
    """커서 아래 커맨드의 문서.

    접두사를 시뮬레이터와 같은 규칙으로 해석한다. 사용자는 `stru` 라고 치고
    시뮬레이터도 그렇게 받아들이므로, 문서만 다르게 굴면 안 된다.
    """
    section = _manual().for_command(token)
    if section is None:
        # 모호하거나(str → stress/structure) 없는 커맨드다. 둘 다 "문서 없음"
        # 으로 답한다 — 화면은 어느 쪽이든 보여 줄 것이 없다.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{token!r} 에 해당하는 문서가 없습니다",
        )
    return await detail(section.id)


@router.get("/search")
async def search(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
) -> SearchResponse:
    """본문 검색.

    두 글자 미만은 받지 않는다. 한 글자는 거의 모든 섹션에 걸려서 결과가
    의미를 잃는다.
    """
    hits = _manual().search(q, limit=limit)
    return SearchResponse(
        query=q,
        hits=[
            SearchHitResponse(
                id=hit.section.id,
                title=hit.section.title,
                command=hit.section.command,
                kind=hit.section.kind,
                snippet=hit.snippet,
            )
            for hit in hits
        ],
    )
