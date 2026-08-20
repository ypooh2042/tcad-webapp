"""메시를 다시 짜기 위한 기하 추출.

새 메시가 **형상을 그대로 유지**하려면 무엇을 고정해야 하는지 정확히 알아야
한다. 고정할 것은 두 가지다.

    바깥 경계 — 건너편에 요소가 없는 변. 경계 조건 코드가 여기 붙어 있다.
    물질 계면 — 건너편 요소의 영역이 다른 변. 물리적 경계다.

이 둘을 gmsh 에 제약으로 주면 안쪽만 다시 짜여 형상이 보존된다.
"""

from __future__ import annotations

from pathlib import Path

from app.remesh.geometry import constrained_segments, region_loops
from app.str_parser.parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return parse_structure((FIXTURES / name).read_text())


class TestConstrainedSegments:
    def test_finds_the_outer_boundary(self) -> None:
        segments = constrained_segments(load("2d_substrate.str"))

        assert any(s.is_outer for s in segments)

    def test_outer_segments_carry_a_boundary_code(self) -> None:
        # 경계 조건은 `t` 라인의 음수 이웃 코드에만 있다. 여기서 놓치면
        # 새 메시가 노출면·뒷면을 잃는다.
        outer = [s for s in constrained_segments(load("2d_substrate.str")) if s.is_outer]

        assert outer
        assert all(s.bc < 0 for s in outer)

    def test_each_segment_appears_once(self) -> None:
        """계면은 양쪽 요소가 각각 들고 있다. 중복으로 세면 gmsh 가 겹친 선을 받는다."""
        segments = constrained_segments(load("2d_cmos_source.str"))
        keys = [(min(s.a, s.b), max(s.a, s.b)) for s in segments]

        assert len(keys) == len(set(keys))

    def test_interfaces_know_both_sides(self) -> None:
        segments = constrained_segments(load("2d_cmos_source.str"))
        interfaces = [s for s in segments if not s.is_outer]

        assert interfaces
        for s in interfaces:
            assert s.left_region != s.right_region

    def test_interior_edges_are_not_constrained(self) -> None:
        """안쪽 변까지 고정하면 다시 짤 것이 남지 않는다."""
        structure = load("2d_cmos_source.str")
        every_edge = set()
        for e in structure.elements:
            v = e.vertices
            for i in range(3):
                every_edge.add((min(v[i], v[(i + 1) % 3]), max(v[i], v[(i + 1) % 3])))

        segments = constrained_segments(structure)

        assert len(segments) < len(every_edge)


class TestRegionLoops:
    def test_every_region_gets_at_least_one_loop(self) -> None:
        structure = load("2d_cmos_source.str")

        loops = region_loops(structure)

        used = {r.id for r in structure.regions if any(
            e.region_id == r.id for e in structure.elements)}
        assert set(loops) == used

    def test_loops_are_closed(self) -> None:
        for region, loops in region_loops(load("2d_cmos_source.str")).items():
            for loop in loops:
                assert loop[0] == loop[-1], f"영역 {region} 의 루프가 닫히지 않았다"

    def test_loop_covers_the_region_area(self) -> None:
        """루프로 잰 넓이가 그 영역 삼각형 넓이 합과 같아야 한다.

        루프를 잘못 이으면 여기서 드러난다 — 형상이 달라졌다는 뜻이다.
        """
        structure = load("2d_cmos_source.str")
        coords = structure.coordinates

        for region, loops in region_loops(structure).items():
            from_loops = 0.0
            for loop in loops:
                acc = 0.0
                for i in range(len(loop) - 1):
                    p, q = coords[loop[i]], coords[loop[i + 1]]
                    acc += p.x * q.y - q.x * p.y
                from_loops += abs(acc) / 2

            from_tris = 0.0
            for e in structure.elements:
                if e.region_id != region:
                    continue
                a, b, c = (coords[i] for i in e.vertices)
                from_tris += abs(
                    (b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)
                ) / 2

            assert from_loops == __import__("pytest").approx(from_tris, rel=1e-6)
