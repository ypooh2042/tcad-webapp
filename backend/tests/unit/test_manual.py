"""매뉴얼 조회와 검색.

SUPREM-IV.GS 매뉴얼(320쪽 PDF)에서 뽑아낸 데이터를 화면이 쓸 수 있게 다듬는다.
카탈로그(app/catalog)와 역할이 다르다:

    카탈로그 = 문법. 파라미터 이름·타입·기본값·제약. suprem.key 에서 나온다.
    매뉴얼   = 산문. 이 커맨드가 무엇을 하는지, 어떻게 쓰는지. PDF 에서 나온다.

둘 다 필요하다. 카탈로그만 있으면 `dose` 가 float 이라는 것만 알고 무슨 뜻인지
모르며, 매뉴얼만 있으면 이름이 11자로 잘린다는 사실을 모른다.
"""

from __future__ import annotations

import pytest

from app.docs.manual import Manual, load_manual


@pytest.fixture(scope="module")
def manual() -> Manual:
    return load_manual()


class TestLoading:
    def test_loads_every_section(self, manual) -> None:
        assert len(manual.sections) == 78

    def test_has_command_reference_pages(self, manual) -> None:
        commands = [s for s in manual.sections if s.kind == "command"]

        assert len(commands) == 50

    def test_sections_carry_page_numbers(self, manual) -> None:
        """매뉴얼 원본을 같이 보려는 사람이 쪽수를 찾을 수 있어야 한다."""
        section = manual.get("implant")

        assert section.pdf_page_start > 0
        assert section.pdf_page_end >= section.pdf_page_start


class TestLookup:
    def test_finds_by_command_name(self, manual) -> None:
        assert manual.for_command("implant").id == "implant"

    def test_resolves_a_prefix(self, manual) -> None:
        """사용자는 `stru` 라고 친다. 시뮬레이터가 그렇게 해석하기 때문이다."""
        assert manual.for_command("stru").command == "structure"

    def test_ambiguous_prefix_has_no_answer(self, manual) -> None:
        """`str` 은 stress 와 structure 사이에서 모호하다."""
        assert manual.for_command("str") is None

    def test_unknown_command_has_no_answer(self, manual) -> None:
        assert manual.for_command("zzzzz") is None

    def test_lookup_is_case_sensitive(self, manual) -> None:
        """시뮬레이터가 대소문자를 구분하므로 문서도 같아야 한다."""
        assert manual.for_command("IMPLANT") is None

    def test_unknown_section_id_raises(self, manual) -> None:
        with pytest.raises(KeyError):
            manual.get("존재하지-않는-섹션")


class TestContent:
    def test_command_sections_have_a_synopsis(self, manual) -> None:
        """SYNOPSIS 는 쓸 수 있는 파라미터 조합을 한눈에 보여준다."""
        commands = [s for s in manual.sections if s.kind == "command"]

        assert all("SYNOPSIS" in s.subsections for s in commands)

    def test_command_sections_have_a_description(self, manual) -> None:
        commands = [s for s in manual.sections if s.kind == "command"]

        assert all("DESCRIPTION" in s.subsections for s in commands)

    def test_description_is_real_prose(self, manual) -> None:
        text = manual.get("diffuse").subsections["DESCRIPTION"]

        assert "diffusion" in text.lower()
        assert len(text) > 200


class TestSearch:
    def test_finds_sections_by_word(self, manual) -> None:
        hits = manual.search("oxidation")

        assert hits
        assert any(hit.section.command == "diffuse" for hit in hits)

    def test_ranks_title_matches_first(self, manual) -> None:
        """`implant` 를 찾는 사람은 implant 커맨드 문서를 먼저 보고 싶다.
        그 낱말은 다른 섹션 본문에도 수없이 나온다."""
        hits = manual.search("implant")

        assert hits[0].section.command == "implant"

    def test_returns_a_snippet_around_the_match(self, manual) -> None:
        """어느 대목에서 걸렸는지 보여줘야 목록을 훑을 수 있다."""
        hit = manual.search("oxidation")[0]

        assert hit.snippet
        assert "oxid" in hit.snippet.lower()

    def test_search_is_case_insensitive(self, manual) -> None:
        """검색은 시뮬레이터 입력이 아니라 사람의 질문이다."""
        assert manual.search("OXIDATION")

    def test_empty_query_finds_nothing(self, manual) -> None:
        assert manual.search("   ") == ()

    def test_unmatched_query_finds_nothing(self, manual) -> None:
        assert manual.search("zzzznotinthemanual") == ()

    def test_limits_the_number_of_hits(self, manual) -> None:
        """흔한 낱말은 거의 모든 섹션에 걸린다. 다 돌려주면 화면이 못 쓴다."""
        assert len(manual.search("the", limit=5)) <= 5
