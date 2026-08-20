"""새 메시를 `.str` 구조로 조립하기.

가장 놓치기 쉬운 두 가지를 본다.

    이웃·경계조건 — SUPREM 은 `t` 라인의 이웃 필드에만 경계 조건을 담는다.
                    새 경계 변은 옛 경계 변 위에 있으므로 코드를 물려받는다.
                    잃으면 노출면·뒷면이 사라져 산화가 엉뚱해진다.
    노드 모델     — 노드는 (점, 물질) 하나씩. 계면 점은 여러 줄이 나온다.
"""

from __future__ import annotations

from pathlib import Path

from app.remesh.assemble import assemble
from app.remesh.msh import Mesh, MeshTriangle
from app.str_parser.boundary import BoundaryCondition
from app.str_parser.parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return parse_structure((FIXTURES / name).read_text())


def same_mesh(structure) -> Mesh:
    """옛 메시를 그대로 새 메시인 척 넘긴다.

    이러면 조립 결과가 원본과 같아야 하므로, 조립 자체의 오류를 메시 변화와
    섞이지 않게 볼 수 있다.
    """
    return Mesh(
        points=tuple((c.x, c.y) for c in structure.coordinates),
        triangles=tuple(
            MeshTriangle(t.vertices, t.region_id) for t in structure.elements
        ),
    )


class TestAssemble:
    def test_keeps_every_triangle(self) -> None:
        structure = load("2d_cmos_source.str")

        built = assemble(structure, same_mesh(structure))

        assert len(built.elements) == len(structure.elements)

    def test_restores_boundary_codes(self) -> None:
        structure = load("2d_cmos_source.str")

        built = assemble(structure, same_mesh(structure))

        def codes(s):
            return sorted(n for e in s.elements for n in e.neighbors if n < 0)

        assert codes(built) == codes(structure)

    def test_boundary_codes_are_known_kinds(self) -> None:
        built = assemble(load("2d_substrate.str"), same_mesh(load("2d_substrate.str")))

        for element in built.elements:
            for n in element.neighbors:
                if n < 0:
                    assert BoundaryCondition.resolve(n) is not BoundaryCondition.UNKNOWN

    def test_neighbours_are_mutual(self) -> None:
        """A 가 B 를 이웃으로 적으면 B 도 A 를 적어야 한다."""
        structure = load("2d_cmos_source.str")

        built = assemble(structure, same_mesh(structure))

        for i, element in enumerate(built.elements):
            for n in element.neighbors:
                if n >= 0:
                    assert i in built.elements[n].neighbors

    def test_writes_one_node_per_material_at_an_interface(self) -> None:
        structure = load("2d_cmos_source.str")

        built = assemble(structure, same_mesh(structure))

        before = {(s.coordinate_index, s.material_id) for s in structure.solutions}
        after = {(s.coordinate_index, s.material_id) for s in built.solutions}
        assert after == before

    def test_values_survive_the_trip(self) -> None:
        structure = load("2d_cmos_source.str")

        built = assemble(structure, same_mesh(structure))

        original = {
            (s.coordinate_index, s.material_id): s.values for s in structure.solutions
        }
        for node in built.solutions:
            got = original[(node.coordinate_index, node.material_id)]
            for a, b in zip(node.values, got):
                assert abs(a - b) <= abs(b) * 1e-9 + 1e-30
