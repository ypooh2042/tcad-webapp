"""SUPREM-IV.GS 매뉴얼 조회와 검색.

원본은 레포에 들어 있는 320쪽 PDF 다. tools/docs/extract_docs.py 가 그것을
섹션 단위 JSON 으로 뽑아 두었고(app/docs/data/manual.json), 여기서는 그 결과를
읽어 조회·검색만 한다. 추출은 pdftotext 를 필요로 하므로 배포 시점이 아니라
개발 시점에 한 번 돌리고 결과를 레포에 넣는다.

**카탈로그와 역할이 다르다.**
    카탈로그(app/catalog) = 문법. 이름·타입·기본값·제약. suprem.key 에서.
    매뉴얼(여기)          = 산문. 무엇을 하는 커맨드인지. PDF 에서.

둘 다 필요하다 — 카탈로그만 있으면 `dose` 가 float 이라는 것만 알고 무슨 뜻인지
모르고, 매뉴얼만 있으면 이름이 11자로 잘린다는 사실을 모른다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.catalog.resolution import Resolution, resolve

_DATA_PATH = Path(__file__).resolve().parent / "data" / "manual.json"

#: 검색 결과에 붙일 발췌 길이. 너무 짧으면 문맥이 안 보이고, 너무 길면 목록을
#: 훑을 수 없다.
_SNIPPET_CHARS = 160

#: 제목에 걸린 결과에 더해 주는 점수. 흔한 낱말은 본문 어디에나 나오므로,
#: 그 낱말이 제목인 섹션이 위로 오지 않으면 검색이 쓸모없어진다.
_TITLE_BONUS = 1000


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    kind: str
    title: str
    #: 이 섹션이 설명하는 커맨드. 챕터·예제 섹션은 None.
    command: str | None
    aliases: tuple[str, ...]
    #: 매뉴얼에 인쇄된 쪽 번호(원본을 같이 볼 때 필요하다).
    page_start: str
    page_end: str
    #: PDF 파일 안에서의 쪽 번호. 인쇄 번호와 다를 수 있다.
    pdf_page_start: int
    pdf_page_end: int
    #: SYNOPSIS / DESCRIPTION / EXAMPLES ...
    subsections: dict[str, str]
    key_parameters: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(self.subsections.values())


@dataclass(frozen=True, slots=True)
class SearchHit:
    section: Section
    score: int
    #: 걸린 대목 주변 발췌.
    snippet: str


@dataclass(frozen=True, slots=True)
class Manual:
    sections: tuple[Section, ...]

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(s.command for s in self.sections if s.command)

    def get(self, section_id: str) -> Section:
        """섹션 id 로 조회한다.

        Raises:
            KeyError: 없는 id 일 때.
        """
        for section in self.sections:
            if section.id == section_id:
                return section
        raise KeyError(section_id)

    def for_command(self, token: str) -> Section | None:
        """커맨드 이름(또는 접두사)으로 문서를 찾는다.

        접두사 해석은 시뮬레이터와 같은 규칙을 쓴다 — 사용자는 `stru` 라고 치고
        시뮬레이터도 그렇게 받아들이므로, 문서만 다르게 굴면 안 된다. 모호하면
        답을 내지 않는다(시뮬레이터도 거절한다).
        """
        match = resolve(token, self.command_names)
        if match.status is not Resolution.RESOLVED:
            return None
        return next(s for s in self.sections if s.command == match.name)

    def search(self, query: str, limit: int = 20) -> tuple[SearchHit, ...]:
        """본문에서 낱말을 찾는다.

        검색은 시뮬레이터 입력이 아니라 사람의 질문이므로 대소문자를 가리지
        않는다(커맨드 해석과 반대다).
        """
        needle = query.strip().lower()
        if not needle:
            return ()

        hits: list[SearchHit] = []
        for section in self.sections:
            haystack = section.text.lower()
            count = haystack.count(needle)
            title = section.title.lower()

            in_title = needle in title or needle == (section.command or "")
            if not count and not in_title:
                continue

            hits.append(
                SearchHit(
                    section=section,
                    score=count + (_TITLE_BONUS if in_title else 0),
                    snippet=_snippet(section.text, needle),
                )
            )

        hits.sort(key=lambda hit: (-hit.score, hit.section.id))
        return tuple(hits[:limit])


def _snippet(text: str, needle: str) -> str:
    """걸린 대목 주변을 잘라 낸다. 없으면 앞부분을 준다(제목만 걸린 경우)."""
    position = text.lower().find(needle)
    if position < 0:
        return _collapse(text[:_SNIPPET_CHARS])

    start = max(0, position - _SNIPPET_CHARS // 3)
    end = min(len(text), position + _SNIPPET_CHARS)
    piece = _collapse(text[start:end])
    return ("…" if start else "") + piece + ("…" if end < len(text) else "")


def _collapse(text: str) -> str:
    """줄바꿈과 연속 공백을 하나로 만든다. 매뉴얼은 고정폭으로 조판돼 있어
    그대로 두면 목록에서 줄이 깨진다."""
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def load_manual(path: Path | None = None) -> Manual:
    """매뉴얼 데이터를 읽는다. 프로세스당 한 번만 파싱한다(368KB)."""
    raw = json.loads((path or _DATA_PATH).read_text())
    return Manual(
        sections=tuple(
            Section(
                id=s["id"],
                kind=s["kind"],
                title=s["title"],
                command=s["command"],
                aliases=tuple(s["aliases"]),
                page_start=s["page_start"],
                page_end=s["page_end"],
                pdf_page_start=s["pdf_page_start"],
                pdf_page_end=s["pdf_page_end"],
                subsections=s["subsections"],
                key_parameters=tuple(s["key_parameters"]),
            )
            for s in raw["sections"]
        )
    )
