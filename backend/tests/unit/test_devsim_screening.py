"""해석할 수 있는 구조인지 가려낸다.

전극이 없는 구조를 목록에 올려 두면, 사용자는 고른 뒤에야 "전극이 없습니다"를
본다. 스무 단계짜리 흐름에서 어느 단계부터 되는지 하나씩 눌러 보게 된다.

가려내는 기준은 **알루미늄이 실리콘이나 폴리실리콘에 닿았는가** 하나다. 금속이
산화막에만 닿은 것은 전극이 아니다 — 전위는 걸려도 전류가 드나들 곳이 없다.

두 단계로 본다. 파싱은 파일 하나에 100 ms 가까이 걸리고 25단계 흐름이면 그것이
스물다섯 번이라, 목록을 여는 것만으로 몇 초가 든다. 먼저 글자만 훑어 알루미늄
영역이 있는 파일로 좁힌 뒤(실측 26개 17MB 를 76 ms) 그것만 제대로 읽는다.
"""

from pathlib import Path

import pytest

from app.devsim.screening import (
    analysable,
    has_driveable_contact,
    mentions_metal,
)
from app.plotting.loader import clear_cache
from app.str_parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


class TestMentionsMetal:
    def test_finds_an_aluminium_region(self) -> None:
        raw = (FIXTURES / "2d_contacts.str").read_bytes()
        assert mentions_metal(raw) is True

    def test_says_no_when_there_is_none(self) -> None:
        raw = (FIXTURES / "2d_cmos_source.str").read_bytes()
        assert mentions_metal(raw) is False

    def test_ignores_other_materials(self) -> None:
        # 폴리(4)나 광저항(7)을 알루미늄(6)으로 착각하면 안 된다.
        assert mentions_metal(b"r 1   4\nr 2   7\n") is False
        assert mentions_metal(b"r 1   4\nr 2   6\n") is True

    def test_does_not_match_other_records(self) -> None:
        # 삼각형 줄에도 6 이 얼마든지 나온다.
        assert mentions_metal(b"t 1 6 6 6 -1024 -1024 -1024\n") is False

    def test_survives_windows_line_endings(self) -> None:
        assert mentions_metal(b"r 1   6\r\n") is True


class TestHasDriveableContact:
    def test_true_when_metal_touches_silicon(self) -> None:
        structure = parse_structure((FIXTURES / "2d_contacts.str").read_text())
        assert has_driveable_contact(structure) is True

    def test_false_before_metallisation(self) -> None:
        structure = parse_structure((FIXTURES / "2d_cmos_source.str").read_text())
        assert has_driveable_contact(structure) is False


class TestAnalysable:
    def test_accepts_a_structure_with_contacts(self) -> None:
        assert analysable(FIXTURES / "2d_contacts.str") is True

    def test_rejects_one_without(self) -> None:
        assert analysable(FIXTURES / "2d_cmos_source.str") is False

    def test_a_missing_file_is_not_analysable(self, tmp_path) -> None:
        # 산출물이 청소된 뒤일 수 있다. 목록을 만들다 터지면 안 된다.
        assert analysable(tmp_path / "gone.str") is False

    def test_a_broken_file_is_not_analysable(self, tmp_path) -> None:
        broken = tmp_path / "broken.str"
        broken.write_text("r 1   6\n이건 구조 파일이 아니다\n")
        assert analysable(broken) is False
