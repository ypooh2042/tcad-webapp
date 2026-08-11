"""메시 기하 계산.

`t` 라인의 의미는 suprem 바이너리 역어셈블로 확정했다:

    t <elem_id> <region_id> <정점 nvrt개> <이웃 nedg개> <미확정 2개>

정점은 1-based 좌표 인덱스(파싱 시 0-based 로 변환), 이웃은 1-based 요소 id 이며
음수면 경계 조건 코드다. **`neighbors[i]` 는 정점 i 의 맞은편 변을 공유하는 요소**다.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from math import hypot

from app.str_parser.boundary import BoundaryCondition
from app.str_parser.models import Element, Structure

_TRIANGLE_VERTICES = 3


@dataclass(frozen=True, slots=True)
class Triangle:
    """렌더링용 삼각형."""

    element_id: int
    vertices: tuple[int, int, int]
    region_id: int
    material: str


@dataclass(frozen=True, slots=True)
class BoundaryEdge:
    """메시 바깥 경계를 이루는 변."""

    element_id: int
    vertices: tuple[int, int]
    condition: BoundaryCondition
    length: float


def signed_area(structure: Structure, element: Element) -> float:
    """삼각형의 부호 있는 면적.

    y 축은 웨이퍼 안쪽(깊이 방향)이 양수다. 모든 예제 파일에서 이 값이 양수이며,
    부호가 섞이면 정점 순서가 일관되지 않다는 뜻이라 컨투어가 뒤집힌다.
    """
    _require_2d(structure)
    a, b, c = (structure.coordinates[v] for v in element.vertices)
    return 0.5 * ((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y))


def total_area(structure: Structure) -> float:
    """전체 메시 면적. 도메인 크기와 대조하면 메시 해석이 맞는지 검증된다."""
    return sum(signed_area(structure, e) for e in structure.elements)


def triangles(structure: Structure) -> Iterator[Triangle]:
    """물질 이름이 붙은 삼각형을 순회한다."""
    _require_2d(structure)
    material_by_region = {r.id: r.material for r in structure.regions}
    for element in structure.elements:
        a, b, c = element.vertices
        yield Triangle(
            element_id=element.id,
            vertices=(a, b, c),
            region_id=element.region_id,
            material=material_by_region[element.region_id],
        )


def boundary_edges(structure: Structure) -> tuple[BoundaryEdge, ...]:
    """경계 변 목록.

    이웃 슬롯이 음수인 자리마다 변이 하나씩 생긴다. 정점 i 의 맞은편 변은
    나머지 두 정점을 잇는 변이다.
    """
    _require_2d(structure)
    edges: list[BoundaryEdge] = []
    for element in structure.elements:
        for i, neighbor in enumerate(element.neighbors):
            if neighbor >= 0:
                continue
            first = element.vertices[(i + 1) % _TRIANGLE_VERTICES]
            second = element.vertices[(i + 2) % _TRIANGLE_VERTICES]
            start = structure.coordinates[first]
            end = structure.coordinates[second]
            edges.append(
                BoundaryEdge(
                    element_id=element.id,
                    vertices=(first, second),
                    condition=BoundaryCondition.resolve(neighbor),
                    length=hypot(end.x - start.x, end.y - start.y),
                )
            )
    return tuple(edges)


def _require_2d(structure: Structure) -> None:
    if structure.dimension != 2:
        raise ValueError(
            f"2D 구조에서만 쓸 수 있습니다 (현재 {structure.dimension}D)"
        )
