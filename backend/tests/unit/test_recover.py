"""panic 으로 죽은 실행을 마지막 체크포인트에서 다시 잇기.

**정상 실행은 이 코드를 지나가지도 않는다.** 성공한 실행을 건드리면 결과가
달라지므로, 오직 죽었을 때만 개입한다.

왜 이어 붙이기가 통하는가: `.str` 은 좌표·영역·삼각형·물성값을 다 담지만
점마다의 목표 격자간격(`pt[]->spac`)은 담지 않는다. 그 값이 공정 내내 쌓여
문제를 만드는데, 파일로 나갔다 들어오면 씻긴다 — 실측으로 6e13 흐름이 통째로는
step 17 에서 죽지만 step 16 결과에서 다시 시작하면 남은 36 단계를 완주했다.
"""

from __future__ import annotations

from pathlib import Path

from app.runner.recover import Checkpoint, find_checkpoint, needs_remesh

SOURCE = """initialize boron conc=1e15
structure out=a.str
deposit oxide thick=0.1
structure out=b.str
diffuse time=10 temp=1000
structure out=c.str
"""


class TestFindCheckpoint:
    def test_picks_the_last_structure_that_exists(self, tmp_path: Path) -> None:
        (tmp_path / "a.str").write_text("x")
        (tmp_path / "b.str").write_text("x")

        found = find_checkpoint(SOURCE, tmp_path)

        assert found is not None
        assert found.structure.name == "b.str"

    def test_remaining_source_starts_after_the_checkpoint(self, tmp_path: Path) -> None:
        (tmp_path / "a.str").write_text("x")
        (tmp_path / "b.str").write_text("x")

        found = find_checkpoint(SOURCE, tmp_path)

        assert found.remaining.startswith("structure in=b.str")
        assert "diffuse time=10" in found.remaining
        # 체크포인트 이전 명령을 다시 돌리면 산출물이 뒤죽박죽이 된다.
        assert "deposit oxide" not in found.remaining

    def test_ignores_the_panic_dump(self, tmp_path: Path) -> None:
        """`panic.str` 은 죽으면서 남긴 것이라 이어 갈 수 없다."""
        (tmp_path / "a.str").write_text("x")
        (tmp_path / "panic.str").write_text("x")

        found = find_checkpoint(SOURCE, tmp_path)

        assert found.structure.name == "a.str"

    def test_nothing_to_resume_from(self, tmp_path: Path) -> None:
        assert find_checkpoint(SOURCE, tmp_path) is None

    def test_nothing_left_to_do(self, tmp_path: Path) -> None:
        """마지막 구조까지 다 나왔으면 이어 갈 것이 없다."""
        for name in ("a.str", "b.str", "c.str"):
            (tmp_path / name).write_text("x")

        assert find_checkpoint(SOURCE, tmp_path) is None


class TestNeedsRemesh:
    """격자가 병적일 때만 다시 짠다.

    다시 시작하는 것만으로 낫는 경우가 많고, 재메시는 값 보간 오차를 들여온다.
    그래서 **퇴화의 흔적이 있을 때만** 쓴다 — 판정은 sub-nm 변이다. 식각·증착이
    남기는 그 점들이 이번 세션에서 추적한 사망의 앞자리에 늘 있었다.
    """

    def test_flags_a_mesh_with_sub_nanometre_edges(self) -> None:
        structure = _square(edge=5.0e-5)      # 0.5 nm

        assert needs_remesh(structure)

    def test_leaves_a_healthy_mesh_alone(self) -> None:
        structure = _square(edge=0.05)        # 50 nm

        assert not needs_remesh(structure)

    def test_ignores_one_dimensional_structures(self) -> None:
        from app.str_parser.parser import parse_structure

        fixture = Path(__file__).parent.parent / "fixtures" / "1d_boron.str"

        assert not needs_remesh(parse_structure(fixture.read_text()))


def _square(edge: float):
    """정사각형 두 삼각형짜리 최소 구조."""
    from app.str_parser.parser import parse_structure

    text = (
        "v test\nD 2 3 3\n"
        f"c 1 0 0  0\nc 2 {edge:g} 0  0\nc 3 {edge:g} {edge:g}  0\nc 4 0 {edge:g}  0\n"
        "r 1   3\n"
        "t 1 1 1 2 3 2 -1024 -1024 -1 -1 \n"
        "t 2 1 1 3 4 -1024 -1024 1 -1 -1 \n"
        "M 0 1.000000e+03\ns 1   5\n"
        "n 0   3   1.000000e+15\nn 1   3   1.000000e+15\n"
        "n 2   3   1.000000e+15\nn 3   3   1.000000e+15\n"
        "I 1   0\n"
    )
    return parse_structure(text)
