"""2D 컨투어용 삼각형 페이로드.

**값을 정점마다 공유하지 않고 삼각형마다 따로 싣는다.** 계면 점은 물질에 따라
값이 다르기 때문이다. CMOS 예제의 (2.0, 0.0419) 지점에서 chem_boron 은 oxide 쪽
1.03e17, silicon 쪽 2.07e16 이다. 정점 하나에 값 하나만 두면 계면에서 어느 한
쪽 값이 반대쪽 물질까지 번져 나간다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.plotting.quantities import value_of
from app.str_parser.models import Structure


@dataclass(frozen=True, slots=True)
class Surface:
    quantity: str
    #: 좌표 배열. triangles 의 인덱스가 여기를 가리킨다.
    x: tuple[float, ...]
    y: tuple[float, ...]
    triangles: tuple[tuple[int, int, int], ...]
    #: 삼각형별 정점 3개의 값. triangles 와 같은 순서다.
    values: tuple[tuple[float, float, float], ...]
    materials: tuple[str, ...]

    @property
    def value_range(self) -> tuple[float, float]:
        flat = [v for triple in self.values for v in triple]
        if not flat:
            return (0.0, 0.0)
        return (min(flat), max(flat))


def build_surface(structure: Structure, quantity: str) -> Surface:
    """2D 구조를 렌더링용 삼각형 목록으로 편다."""
    if structure.dimension != 2:
        raise ValueError(
            f"2D 구조에서만 쓸 수 있습니다 (현재 {structure.dimension}D)"
        )

    region_by_id = {region.id: region for region in structure.regions}

    triangles: list[tuple[int, int, int]] = []
    values: list[tuple[float, float, float]] = []
    materials: list[str] = []

    for element in structure.elements:
        region = region_by_id[element.region_id]
        try:
            triple = tuple(
                value_of(
                    structure.solution_at(vertex, region.material_id), quantity
                )
                for vertex in element.vertices
            )
        except KeyError:
            # 이 요소의 물질 쪽 해가 없다. 다른 물질 값으로 채우면 계면에서
            # 값이 번지므로 요소를 통째로 뺀다.
            continue

        a, b, c = element.vertices
        triangles.append((a, b, c))
        values.append(triple)  # type: ignore[arg-type]
        materials.append(region.material)

    return Surface(
        quantity=quantity,
        x=tuple(coordinate.x for coordinate in structure.coordinates),
        y=tuple(coordinate.y for coordinate in structure.coordinates),
        triangles=tuple(triangles),
        values=tuple(values),
        materials=tuple(materials),
    )
