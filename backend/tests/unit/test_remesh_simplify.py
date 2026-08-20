"""경계 단순화.

경계를 글자 그대로 보존하면 식각이 남긴 sub-nm 선분이 그대로 남고, 그 자리가
새 메시의 품질을 끌어내린다(실측: 경계를 보존한 재메시의 최소각이 3~13° 에
머물렀다). 그래서 **의미 없이 촘촘한 점만** 걷어낸다.

두 가지를 반드시 지킨다.

    모서리    — 물질 조합이나 경계 조건이 바뀌는 점, 세 갈래 이상이 만나는 점.
                여기를 지우면 위상이 달라진다.
    형상 오차 — 점을 지워 경계가 움직이는 거리를 허용오차 이하로 묶는다.
"""

from __future__ import annotations

from pathlib import Path

from app.remesh.geometry import constrained_segments
from app.remesh.simplify import simplify_boundary
from app.str_parser.parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return parse_structure((FIXTURES / name).read_text())


class TestSimplify:
    def test_drops_points_on_a_straight_run(self) -> None:
        structure = load("2d_substrate.str")

        kept = simplify_boundary(structure, tolerance=1.0)

        every = {i for s in constrained_segments(structure) for i in (s.a, s.b)}
        assert kept < every

    def test_keeps_everything_at_zero_tolerance(self) -> None:
        """허용오차가 0 이면 아무것도 지우지 않는다 — 형상이 그대로다."""
        structure = load("2d_cmos_source.str")

        kept = simplify_boundary(structure, tolerance=0.0)

        every = {i for s in constrained_segments(structure) for i in (s.a, s.b)}
        assert kept == every

    def test_keeps_junctions(self) -> None:
        """세 갈래가 만나는 점을 지우면 영역 경계가 어긋난다."""
        structure = load("2d_cmos_source.str")
        degree: dict[int, int] = {}
        for s in constrained_segments(structure):
            for i in (s.a, s.b):
                degree[i] = degree.get(i, 0) + 1
        junctions = {i for i, d in degree.items() if d > 2}

        kept = simplify_boundary(structure, tolerance=1e9)

        assert junctions <= kept

    def test_keeps_points_where_the_material_pair_changes(self) -> None:
        structure = load("2d_cmos_source.str")
        sides: dict[int, set] = {}
        for s in constrained_segments(structure):
            for i in (s.a, s.b):
                sides.setdefault(i, set()).add(
                    (s.left_region, s.right_region, s.bc)
                )
        corners = {i for i, kinds in sides.items() if len(kinds) > 1}

        kept = simplify_boundary(structure, tolerance=1e9)

        assert corners <= kept

    def test_bounds_the_shape_error(self) -> None:
        """지워진 점이 **남은 경계선**에서 허용오차보다 멀면 형상이 바뀐 것이다.

        남은 *점* 까지의 거리가 아니다 — 직선 구간에서는 중간 점이 양 끝에서
        멀어도 경계는 그대로다. 재야 할 것은 선까지의 거리다.
        """
        from app.remesh.simplify import _offset

        structure = load("2d_cmos_source.str")
        tolerance = 5.0e-4          # cm 단위. 넉넉히 줘서 실제로 지우게 한다.
        coords = structure.coordinates

        kept = simplify_boundary(structure, tolerance=tolerance)

        segments = constrained_segments(structure)
        every = {i for s in segments for i in (s.a, s.b)}
        dropped = every - kept
        assert dropped, "지운 점이 없으면 이 시험이 아무것도 확인하지 않는다"

        # 남은 점들로 다시 이은 경계선.
        neighbours: dict[int, list[int]] = {}
        for s in segments:
            neighbours.setdefault(s.a, []).append(s.b)
            neighbours.setdefault(s.b, []).append(s.a)

        for i in dropped:
            # 이 점이 놓여 있던 구간의 양끝(남은 점)을 찾는다.
            ends = []
            for direction in neighbours[i]:
                current, previous = direction, i
                while current not in kept:
                    nxt = [n for n in neighbours[current] if n != previous]
                    if len(nxt) != 1:
                        break
                    previous, current = current, nxt[0]
                ends.append(current)
            assert len(ends) == 2
            assert _offset(coords[i], coords[ends[0]], coords[ends[1]]) <= tolerance
