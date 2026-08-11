"""SUPREM 의 이름 해석 규칙.

이 파일의 규칙은 추측이 아니라 실제 시뮬레이터(SUPREM-IV.GS B.9305)에 입력을
넣어 확인한 것이다. 판정은 오류 메시지가 아니라 **산출물이 실제로 생겼는지**로
했다. 인식하지 못한 첫 단어는 /bin/bash 로 넘어가기 때문에, 오류 메시지만 보면
실패를 성공으로 오판한다.

확인한 것:
    structure outfile=out.str   → 생성됨
    stru      outfile=out.str   → 생성됨
    str       outfile=out.str   → "the command is ambiguous" (stress/structure)
    STRUCTURE outfile=out.str   → 생성 안 됨 (대소문자 구분)
    structure OUTFILE=out.str   → 생성 안 됨
"""

from __future__ import annotations

import pytest

from app.catalog.resolution import Resolution, resolve

COMMANDS = ("structure", "stress", "select", "selenium", "deposit")


class TestUniquePrefix:
    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ("structure", "structure"),
            ("stru", "structure"),
            ("stre", "stress"),
            ("selec", "select"),
            ("selen", "selenium"),
            ("d", "deposit"),
        ],
    )
    def test_unique_prefix_resolves(self, token, expected) -> None:
        match = resolve(token, COMMANDS)

        assert match.status is Resolution.RESOLVED
        assert match.name == expected

    def test_full_name_resolves(self) -> None:
        assert resolve("deposit", COMMANDS).name == "deposit"


class TestAmbiguity:
    @pytest.mark.parametrize("token", ["s", "st", "str", "sel", "sele"])
    def test_shared_prefix_is_ambiguous(self, token) -> None:
        match = resolve(token, COMMANDS)

        assert match.status is Resolution.AMBIGUOUS

    def test_reports_the_candidates(self) -> None:
        """사용자가 어디까지 더 쳐야 하는지 알려면 후보가 필요하다."""
        match = resolve("str", COMMANDS)

        assert set(match.candidates) == {"structure", "stress"}
        assert match.name is None

    def test_exact_match_does_not_win_over_longer_names(self) -> None:
        """SUPREM 에는 정확 일치 우선 규칙이 없다.

        structure 카드에서 `backside` 를 그대로 써 봤더니 실제로
        "ambiguous parameter - backside" 가 났다. backside.y 가 있기 때문이다.
        즉 backside 는 SUPREM4GS 에서 도달할 수 없는 파라미터다. 여기서 정확
        일치를 우선시키면 카탈로그가 시뮬레이터와 다르게 동작한다.
        """
        match = resolve("backside", ("backside", "backside.y"))

        assert match.status is Resolution.AMBIGUOUS


class TestUnknown:
    def test_no_match_is_unknown(self) -> None:
        match = resolve("zzz", COMMANDS)

        assert match.status is Resolution.UNKNOWN
        assert match.name is None
        assert match.candidates == ()

    def test_longer_than_any_name_is_unknown(self) -> None:
        """접두사 규칙이라 이름보다 긴 토큰은 어디에도 걸리지 않는다."""
        assert resolve("depositing", COMMANDS).status is Resolution.UNKNOWN


class TestCaseSensitivity:
    """대소문자를 섞으면 시뮬레이터는 그 줄을 통째로 /bin/bash 에 넘긴다."""

    @pytest.mark.parametrize("token", ["STRUCTURE", "Structure", "sTru"])
    def test_uppercase_does_not_resolve(self, token) -> None:
        assert resolve(token, COMMANDS).status is Resolution.UNKNOWN


class TestEmptyToken:
    def test_empty_token_matches_everything(self) -> None:
        """빈 토큰은 모든 이름의 접두사다. 규칙대로 모호로 처리한다."""
        match = resolve("", COMMANDS)

        assert match.status is Resolution.AMBIGUOUS
        assert len(match.candidates) == len(COMMANDS)

    def test_empty_name_pool_is_unknown(self) -> None:
        assert resolve("anything", ()).status is Resolution.UNKNOWN
