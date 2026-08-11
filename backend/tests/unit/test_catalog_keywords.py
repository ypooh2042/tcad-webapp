"""인터프리터 키워드와 커맨드가 섞이는 방식.

실제 시뮬레이터로 확인한 것:

    source  → 인터프리터가 처리
    sourc   → /bin/bash 로 샘          (키워드는 접두사로 줄일 수 없다)
    fore    → /bin/bash 로 샘
    set     → 인터프리터가 처리        (키워드는 카드와 별개 공간이다)
    se      → "ambiguous" (select/selenium) 후 /bin/bash 로 샘
    sel     → 위와 같음

즉 첫 단어는 이 순서로 판정된다:
    1. 키워드와 **정확히** 같으면 인터프리터가 가져간다.
    2. 아니면 카드 이름에 대해 **접두사** 해석을 한다.
    3. 그래도 안 되면 통째로 /bin/bash 에 넘어간다.
"""

from __future__ import annotations

import pytest

from app.catalog.catalog import WordKind, load_catalog
from app.catalog.keywords import KEYWORD_NAMES


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


class TestKeywordsAreExactOnly:
    @pytest.mark.parametrize("keyword", ["source", "foreach", "set", "quit"])
    def test_full_keyword_is_recognised(self, catalog, keyword) -> None:
        assert catalog.resolve_word(keyword).kind is WordKind.KEYWORD

    @pytest.mark.parametrize("token", ["sourc", "sour", "fore", "quie"])
    def test_shortened_keyword_is_not_recognised(self, catalog, token) -> None:
        """키워드에는 접두사 해석이 적용되지 않는다."""
        assert catalog.resolve_word(token).kind is not WordKind.KEYWORD


class TestKeywordsAreASeparateNamespace:
    def test_keyword_wins_even_when_cards_are_ambiguous(self, catalog) -> None:
        """`set` 은 select/selenium 과 무관하게 통과한다."""
        assert catalog.resolve_word("set").kind is WordKind.KEYWORD

    @pytest.mark.parametrize("token", ["se", "sel"])
    def test_card_ambiguity_is_unaffected_by_keywords(self, catalog, token) -> None:
        match = catalog.resolve_word(token)

        assert match.kind is WordKind.AMBIGUOUS
        assert "select" in match.candidates
        assert "selenium" in match.candidates

    def test_keywords_do_not_appear_among_card_candidates(self, catalog) -> None:
        """`set` 이 후보에 섞이면 사용자는 카드인 줄 안다."""
        assert "set" not in catalog.resolve_word("se").candidates


class TestCommands:
    def test_unique_prefix_is_a_command(self, catalog) -> None:
        match = catalog.resolve_word("stru")

        assert match.kind is WordKind.COMMAND
        assert match.name == "structure"

    def test_ambiguous_prefix_is_reported(self, catalog) -> None:
        match = catalog.resolve_word("str")

        assert match.kind is WordKind.AMBIGUOUS
        assert set(match.candidates) == {"stress", "structure"}

    def test_unknown_word_falls_through(self, catalog) -> None:
        """어디에도 걸리지 않는 단어는 /bin/bash 로 넘어간다. 사용자에게 이
        사실을 알려줄 수 있어야 오타를 알아챈다."""
        assert catalog.resolve_word("zzzzz").kind is WordKind.UNKNOWN

    def test_uppercase_is_not_a_command(self, catalog) -> None:
        assert catalog.resolve_word("STRUCTURE").kind is WordKind.UNKNOWN


class TestKeywordList:
    def test_bash_builtins_are_not_listed(self) -> None:
        """read/alias/unalias/history 는 인터프리터가 아니라 bash 가 처리했다.

        인자 없이 부르면 bash 가 조용히 성공해서 인터프리터 단어처럼 보인다.
        존재하지 않는 경로를 붙여 다시 확인한 결과 전부 bash 쪽이었다.
        """
        for builtin in ("read", "alias", "unalias", "history"):
            assert builtin not in KEYWORD_NAMES

    def test_prompt_is_not_listed(self) -> None:
        """`prompt` 는 인식되지 않고 그대로 셸로 넘어갔다."""
        assert "prompt" not in KEYWORD_NAMES

    def test_echo_is_a_card_not_a_keyword(self, catalog) -> None:
        """echo 는 suprem.key 에 card 0 으로 정의되어 있다."""
        assert "echo" not in KEYWORD_NAMES
        assert catalog.resolve_word("echo").kind is WordKind.COMMAND
