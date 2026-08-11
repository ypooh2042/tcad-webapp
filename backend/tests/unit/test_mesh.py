"""2D 삼각형 메시 재구성 테스트.

`t` 라인의 의미는 suprem 바이너리의 `ig2_write`/`ig2_read` 를 역어셈블해 확정했다.
레이아웃은 `D` 라인이 결정한다: `D <mode> <nvrt> <nedg>` → 필드 수 = 2+nvrt+nedg+2.

여기 박아둔 수치들은 전부 실측 검증값이다. 값이 바뀌면 메시 해석이 틀어진 것이다.
"""

from pathlib import Path

import pytest

from app.str_parser import parse_structure
from app.str_parser.boundary import BoundaryCondition
from app.str_parser.mesh import (
    boundary_edges,
    signed_area,
    total_area,
    triangles,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def substrate():
    """4µm × 3µm 실리콘 사각형. 기하 검증용 깨끗한 케이스."""
    return parse_structure((FIXTURES / "2d_substrate.str").read_text())


@pytest.fixture(scope="module")
def cmos():
    """S/D implant 직후. poly gate + oxide + silicon."""
    return parse_structure((FIXTURES / "2d_cmos_source.str").read_text())


@pytest.fixture(scope="module")
def boron_1d():
    return parse_structure((FIXTURES / "1d_boron.str").read_text())


class TestDimensionLine:
    """`D <mode> <nvrt> <nedg>` — writer 가 mode/nvrt/nedg 전역을 그대로 출력한다."""

    def test_2d_has_three_vertices_and_neighbors(self, substrate) -> None:
        assert substrate.dimension == 2
        assert substrate.vertices_per_element == 3
        assert substrate.neighbors_per_element == 3

    def test_1d_has_two_vertices_and_neighbors(self, boron_1d) -> None:
        assert boron_1d.dimension == 1
        assert boron_1d.vertices_per_element == 2
        assert boron_1d.neighbors_per_element == 2

    def test_element_field_count_follows_d_line(self, cmos) -> None:
        """필드 수 = 2 + nvrt + nedg + 2."""
        element = cmos.elements[0]
        assert len(element.vertices) == cmos.vertices_per_element
        assert len(element.neighbors) == cmos.neighbors_per_element
        assert len(element.extra) == 2


class TestElementParsing:
    def test_counts_elements(self, cmos) -> None:
        assert len(cmos.elements) == 2617

    def test_vertices_are_zero_based_point_indices(self, cmos) -> None:
        """t 라인의 정점 필드는 1-based 좌표 인덱스 → 0-based 로 변환해 보관."""
        for element in cmos.elements:
            for vertex in element.vertices:
                assert 0 <= vertex < len(cmos.coordinates)

    def test_every_point_is_used(self, substrate) -> None:
        used = {v for e in substrate.elements for v in e.vertices}
        assert len(used) == len(substrate.coordinates)

    def test_region_id_resolves_to_region(self, cmos) -> None:
        region_ids = {r.id for r in cmos.regions}
        assert all(e.region_id in region_ids for e in cmos.elements)

    def test_trailing_fields_are_preserved_verbatim(self, cmos) -> None:
        """의미 미확정 필드. 해석하지 않고 원본 그대로 보존한다."""
        assert all(e.extra == (-1, -1) for e in cmos.elements)


class TestNeighborTopology:
    def test_positive_neighbor_is_zero_based_element_index(self, cmos) -> None:
        for element in cmos.elements:
            for neighbor in element.neighbors:
                if neighbor >= 0:
                    assert neighbor < len(cmos.elements)

    def test_neighbor_links_are_reciprocal(self, cmos) -> None:
        """A가 B를 이웃으로 가리키면 B도 A를 가리켜야 한다."""
        for index, element in enumerate(cmos.elements):
            for neighbor in element.neighbors:
                if neighbor >= 0:
                    assert index in cmos.elements[neighbor].neighbors

    def test_neighbor_is_opposite_the_matching_vertex(self, cmos) -> None:
        """nbrs[i] 는 정점 i 의 맞은편 변을 공유하는 요소다.

        따라서 두 요소는 정점 i 를 뺀 나머지 정점들을 공유한다.
        """
        for index, element in enumerate(cmos.elements):
            for i, neighbor in enumerate(element.neighbors):
                if neighbor < 0:
                    continue
                shared = set(element.vertices) - {element.vertices[i]}
                assert shared <= set(cmos.elements[neighbor].vertices)


class TestBoundaryConditions:
    """음수 sentinel 은 ChosenBC() 가 반환하는 경계 조건 코드다."""

    def test_reflect_code(self) -> None:
        assert BoundaryCondition.resolve(-1024) is BoundaryCondition.REFLECT

    def test_backside_code(self) -> None:
        assert BoundaryCondition.resolve(-1023) is BoundaryCondition.BACKSIDE

    def test_exposed_code(self) -> None:
        assert BoundaryCondition.resolve(-1022) is BoundaryCondition.EXPOSED

    def test_unknown_negative_code_is_not_guessed(self) -> None:
        """정의되지 않은 음수는 임의 해석하지 않는다."""
        assert BoundaryCondition.resolve(-9999) is BoundaryCondition.UNKNOWN

    def test_substrate_sidewalls_are_reflecting(self, substrate) -> None:
        """4×3 사각형: 양 옆면(각 3µm)이 reflect, 합계 6µm."""
        length = sum(
            e.length
            for e in boundary_edges(substrate)
            if e.condition is BoundaryCondition.REFLECT
        )
        assert length == pytest.approx(6.0)

    def test_substrate_bottom_is_backside(self, substrate) -> None:
        edges = [
            e
            for e in boundary_edges(substrate)
            if e.condition is BoundaryCondition.BACKSIDE
        ]
        assert sum(e.length for e in edges) == pytest.approx(4.0)
        assert all(
            substrate.coordinates[v].y == pytest.approx(3.0)
            for e in edges
            for v in e.vertices
        )

    def test_substrate_top_is_exposed(self, substrate) -> None:
        edges = [
            e
            for e in boundary_edges(substrate)
            if e.condition is BoundaryCondition.EXPOSED
        ]
        assert sum(e.length for e in edges) == pytest.approx(4.0)
        assert all(
            substrate.coordinates[v].y == pytest.approx(0.0)
            for e in edges
            for v in e.vertices
        )

    def test_boundary_edge_count_matches_negative_slots(self, cmos) -> None:
        negative_slots = sum(
            1 for e in cmos.elements for n in e.neighbors if n < 0
        )
        assert len(boundary_edges(cmos)) == negative_slots == 165


class TestGeometry:
    def test_substrate_area_is_exactly_domain(self, substrate) -> None:
        """CMOS.in: line x 0~4, line y 0~3 → 12.0 µm²."""
        assert total_area(substrate) == pytest.approx(12.0, abs=1e-9)

    def test_all_elements_have_positive_signed_area(self, cmos) -> None:
        """정점 순서가 일관돼야 컨투어 렌더링이 뒤집히지 않는다."""
        assert all(signed_area(cmos, e) > 0 for e in cmos.elements)

    def test_poly_gate_area_and_position(self, cmos) -> None:
        """poly gate: CMOS.in 에서 x=1.75~2.25(0.5µm), thick=0.4µm → 0.2µm²."""
        poly_regions = {r.id for r in cmos.regions if r.material == "poly"}
        poly = [e for e in cmos.elements if e.region_id in poly_regions]
        assert sum(signed_area(cmos, e) for e in poly) == pytest.approx(0.2, abs=1e-6)

        xs = [cmos.coordinates[v].x for e in poly for v in e.vertices]
        assert min(xs) == pytest.approx(1.75)
        assert max(xs) == pytest.approx(2.25)

    def test_triangles_yield_material_names(self, cmos) -> None:
        materials = {t.material for t in triangles(cmos)}
        assert materials == {"silicon", "oxide", "poly"}

    def test_triangles_rejects_1d_structure(self, boron_1d) -> None:
        with pytest.raises(ValueError, match="2D"):
            list(triangles(boron_1d))


class TestInterfaceValueLookup:
    """계면 정점은 인접 물질마다 값이 다르다. 물질을 지정해 조회해야 한다."""

    def test_same_point_holds_different_values_per_material(self, cmos) -> None:
        """oxide/silicon 계면의 게이트 중앙 지점 (x=2.0, y≈0.0419).

        같은 점인데 chem_boron 이 oxide 쪽 1.03e17, silicon 쪽 2.07e16 으로
        5배 차이난다. 물질을 무시하고 조회하면 컨투어가 계면에서 튄다.
        """
        point = next(
            index
            for index, coordinate in enumerate(cmos.coordinates)
            if coordinate.x == pytest.approx(2.0)
            and coordinate.y == pytest.approx(0.0419063)
        )

        in_oxide = cmos.solution_at(point, 1).value("chem_boron")
        in_silicon = cmos.solution_at(point, 3).value("chem_boron")

        assert in_oxide == pytest.approx(1.030547e17, rel=1e-6)
        assert in_silicon == pytest.approx(2.06709e16, rel=1e-6)

    def test_interface_points_exist_in_multiple_materials(self, cmos) -> None:
        by_point: dict[int, set[int]] = {}
        for solution in cmos.solutions:
            by_point.setdefault(solution.coordinate_index, set()).add(
                solution.material_id
            )
        assert sum(1 for materials in by_point.values() if len(materials) > 1) == 174

    def test_lookup_is_unique_per_point_and_material(self, cmos) -> None:
        seen = {(s.coordinate_index, s.material_id) for s in cmos.solutions}
        assert len(seen) == len(cmos.solutions)

    def test_missing_material_raises_rather_than_guessing(self, cmos) -> None:
        with pytest.raises(KeyError):
            cmos.solution_at(0, 999)
