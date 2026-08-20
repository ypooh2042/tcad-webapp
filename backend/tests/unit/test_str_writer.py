"""`.str` 쓰기.

메시를 다시 짜려면 먼저 **읽은 것을 그대로 되쓸 수 있어야** 한다. 그래야
나중에 생기는 차이를 메시 탓으로 돌릴 수 있다. 그래서 이 파일의 중심은
왕복 항등 — 시뮬레이터가 쓴 파일을 파싱했다가 되쓰면 **바이트 동일**해야
한다.

바이트 동일이 과한 기준처럼 보이지만 그렇지 않다. 형식이 손으로 맞춘
공백까지 포함하고(`n %d   %d  `), 좌표는 `%g`, 물성값은 `%e` 로 자릿수가
정해져 있다. 한 군데라도 어긋나면 되쓴 파일이 시뮬레이터에서 다르게 읽힐 수
있는데, 그것을 눈으로 확인할 방법이 없다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.str_parser.parser import parse_structure
from app.str_parser.writer import write_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"
STRUCTURES = sorted(FIXTURES.glob("*.str"))


def test_fixtures_exist() -> None:
    """픽스처가 사라지면 아래 시험이 조용히 통과한다."""
    assert STRUCTURES, "tests/fixtures 에 .str 이 없습니다"


@pytest.mark.parametrize("path", STRUCTURES, ids=lambda p: p.name)
class TestRoundTrip:
    def test_byte_identical(self, path: Path) -> None:
        original = path.read_text()

        assert write_structure(parse_structure(original), original) == original

    def test_parses_back_to_the_same_structure(self, path: Path) -> None:
        """되쓴 것을 다시 읽어도 같아야 한다. 형식이 아니라 내용의 확인이다."""
        original = path.read_text()
        once = parse_structure(original)

        twice = parse_structure(write_structure(once, original))

        assert twice.coordinates == once.coordinates
        assert twice.elements == once.elements
        assert twice.regions == once.regions
        assert twice.solutions == once.solutions


class TestReplacedMesh:
    """새 메시로 갈아끼우는 것이 이 모듈의 목적이다."""

    def test_writes_the_given_mesh_not_the_original(self) -> None:
        source = (FIXTURES / "2d_substrate.str").read_text()
        structure = parse_structure(source)
        # 삼각형 하나만 남긴다.
        trimmed = structure.__class__(
            **{
                **{f: getattr(structure, f) for f in structure.__slots__},
                "elements": structure.elements[:1],
            }
        )

        written = write_structure(trimmed, source)

        assert len([l for l in written.splitlines() if l.startswith("t ")]) == 1

    def test_keeps_the_records_it_does_not_own(self) -> None:
        """v·D·M·s·I 는 그대로 옮긴다 — 다시 만들 이유가 없고 위험만 크다."""
        source = (FIXTURES / "2d_substrate.str").read_text()

        written = write_structure(parse_structure(source), source)

        for tag in ("v", "D", "M", "s", "I"):
            kept = [l for l in source.splitlines() if l.startswith(f"{tag} ")]
            out = [l for l in written.splitlines() if l.startswith(f"{tag} ")]
            assert out == kept, tag
