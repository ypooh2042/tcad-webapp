"""gmsh 입력(`.geo`) 만들기.

까다로운 곳은 두 군데다.

    방향  — Curve Loop 은 이어지는 선의 **부호**로 방향을 나타낸다. 뒤집힌
            선은 음수로 적어야 하고, 틀리면 gmsh 가 면을 만들지 못한다.
    구멍  — 한 영역이 다른 루프를 품고 있으면(폴리를 감싼 산화막) 그것은
            구멍이다. 따로 떨어진 조각과 구분해야 한다.
"""

from __future__ import annotations

from pathlib import Path

from app.remesh.geo import GeoModel, build_geo
from app.str_parser.parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return parse_structure((FIXTURES / name).read_text())


class TestBuild:
    def test_only_constrained_points_become_points(self) -> None:
        """안쪽 점까지 넣으면 다시 짤 것이 남지 않는다."""
        structure = load("2d_cmos_source.str")

        model = build_geo(structure)

        assert 0 < len(model.points) < len(structure.coordinates)

    def test_every_region_becomes_a_surface(self) -> None:
        structure = load("2d_cmos_source.str")

        model = build_geo(structure)

        used = {e.region_id for e in structure.elements}
        assert {s.region_id for s in model.surfaces} == used

    def test_loop_references_are_signed(self) -> None:
        """부호가 전부 양수면 방향을 안 맞춘 것이다."""
        model = build_geo(load("2d_cmos_source.str"))

        refs = [r for s in model.surfaces for loop in s.loops for r in loop]
        assert any(r < 0 for r in refs)

    def test_line_ids_are_one_based(self) -> None:
        # gmsh 는 0 을 식별자로 받지 않는다.
        model = build_geo(load("2d_cmos_source.str"))

        assert all(abs(r) >= 1 for s in model.surfaces for lp in s.loops for r in lp)


class TestText:
    def test_writes_points_lines_and_surfaces(self) -> None:
        text = build_geo(load("2d_substrate.str")).to_text()

        assert "Point(1)" in text
        assert "Line(1)" in text
        assert "Curve Loop(" in text
        assert "Plane Surface(" in text

    def test_marks_regions_so_triangles_can_be_assigned(self) -> None:
        """어느 삼각형이 어느 물질인지 알아야 .str 로 되쓸 수 있다."""
        text = build_geo(load("2d_cmos_source.str")).to_text()

        assert "Physical Surface" in text

    def test_gives_every_point_a_size(self) -> None:
        # 크기를 안 주면 gmsh 가 전역 기본값으로 덮어 경계 해상도를 잃는다.
        text = build_geo(load("2d_substrate.str")).to_text()
        first = next(l for l in text.splitlines() if l.startswith("Point(1)"))

        assert len(first.split("{")[1].split("}")[0].split(",")) == 4


class TestNesting:
    """한 영역의 루프가 여럿일 때 구멍인지 떨어진 조각인지 갈라야 한다.

    실측: 질화막 마스크 두 개, 게이트 두 개, 스페이서 네 개가 모두 **떨어진
    조각**이다. 전부 구멍으로 치면 그 자리가 통째로 메시에서 빠지고, 계면
    건너편이 비어 경계 조건을 복원할 수 없게 된다.
    """

    def test_disjoint_pieces_become_separate_surfaces(self) -> None:
        from app.remesh.geo import nest_loops

        # 서로 떨어진 두 사각형.
        left = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        right = [(3.0, 0.0), (4.0, 0.0), (4.0, 1.0), (3.0, 1.0)]

        groups = nest_loops([left, right])

        assert len(groups) == 2
        assert all(len(g) == 1 for g in groups)

    def test_a_contained_loop_becomes_a_hole(self) -> None:
        from app.remesh.geo import nest_loops

        outer = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        inner = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]

        groups = nest_loops([outer, inner])

        assert len(groups) == 1
        assert groups[0] == [0, 1]

    def test_an_island_inside_a_hole_is_its_own_surface(self) -> None:
        from app.remesh.geo import nest_loops

        outer = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        hole = [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)]
        island = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]

        groups = nest_loops([outer, hole, island])

        assert sorted(len(g) for g in groups) == [1, 2]


class TestSizeField:
    """안쪽 크기를 따로 정한다.

    경계 점 크기만 주면 gmsh 가 그것을 안쪽까지 퍼뜨려, 경계가 촘촘한 구조에서
    점이 폭발한다(실측: 6,277 → 11,071). 경계는 경계대로 두고 안쪽은 **옛 메시의
    안쪽 밀도**를 목표로 삼는다 — 밀도는 그대로, 품질만 올리는 것이 목적이다.
    """

    def test_lets_boundary_sizes_grade_inward(self) -> None:
        text = build_geo(load("2d_cmos_source.str")).to_text()

        assert "Mesh.MeshSizeExtendFromBoundary = 1" in text

    def test_grades_size_away_from_the_boundary(self) -> None:
        text = build_geo(load("2d_cmos_source.str")).to_text()

        assert "Field[1] = Distance" in text
        assert "Field[2] = Threshold" in text
        # 최종 배경장은 기하 등급과 도핑 기울기 중 **작은 쪽**이다.
        assert "Field[4] = Min" in text
        assert "Background Field = 4" in text

    def test_carries_a_doping_driven_background(self) -> None:
        """기하만 보고 성기게 만들면 접합이 뭉개진다(실측: 비소 13.6% 오차)."""
        model = build_geo(load("2d_cmos_source.str"))

        assert model.background.startswith('View "sizes"')
        assert "ST(" in model.background
        assert "Field[3] = PostView" in model.to_text()

    def test_interior_target_comes_from_the_old_mesh(self) -> None:
        structure = load("2d_cmos_source.str")

        model = build_geo(structure)

        # 옛 안쪽 변 길이의 중앙값 언저리여야 한다.
        import statistics
        from app.remesh.geometry import constrained_segments
        from math import hypot

        fixed = {
            (min(s.a, s.b), max(s.a, s.b)) for s in constrained_segments(structure)
        }
        c = structure.coordinates
        interior = []
        seen = set()
        for e in structure.elements:
            v = e.vertices
            for i in range(3):
                key = (min(v[i], v[(i + 1) % 3]), max(v[i], v[(i + 1) % 3]))
                if key in fixed or key in seen:
                    continue
                seen.add(key)
                interior.append(hypot(c[key[0]].x - c[key[1]].x, c[key[0]].y - c[key[1]].y))

        assert model.interior_size == statistics.median(interior)

    def test_falls_back_when_there_is_no_interior(self) -> None:
        """모든 변이 경계인 아주 성긴 구조도 있다. 0 을 크기로 주면 gmsh 가 멈춘다."""
        model = build_geo(load("2d_substrate.str"))

        assert model.interior_size > 0
