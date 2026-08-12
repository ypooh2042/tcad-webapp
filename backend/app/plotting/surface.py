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
    #: 칠할 물리량. 재질만 보는 단면은 빈 문자열이다.
    quantity: str
    #: 좌표 배열. triangles 의 인덱스가 여기를 가리킨다.
    x: tuple[float, ...]
    y: tuple[float, ...]
    triangles: tuple[tuple[int, int, int], ...]
    #: 삼각형별 정점 3개의 값. triangles 와 같은 순서다. 재질만 보는 단면은
    #: 비어 있다 — 0 을 채워 넣으면 색 범위가 뒤틀린다.
    values: tuple[tuple[float, float, float], ...]
    materials: tuple[str, ...]

    @property
    def value_range(self) -> tuple[float, float]:
        flat = [v for triple in self.values for v in triple]
        if not flat:
            return (0.0, 0.0)
        return (min(flat), max(flat))


def build_surface(structure: Structure, quantity: str | None) -> Surface:
    """2D 구조를 렌더링용 삼각형 목록으로 편다.

    Args:
        quantity: 칠할 물리량. **None 이면 재질만 본다** — 값을 읽지 않으므로
            요소를 하나도 버리지 않는다. 값을 칠할 때는 그 물질에 해가 없는
            요소를 빼야 계면에서 값이 번지지만, 재질을 보여줄 때 층이 빠지면
            그림이 거짓말을 한다(없는 층을 없다고 읽는다).
    """
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

        if quantity is not None:
            try:
                triple = tuple(
                    value_of(
                        structure.solution_at(vertex, region.material_id),
                        quantity,
                    )
                    for vertex in element.vertices
                )
            except KeyError:
                # 이 요소의 물질 쪽 해가 없다. 다른 물질 값으로 채우면 계면에서
                # 값이 번지므로 요소를 통째로 뺀다.
                continue
            values.append(triple)  # type: ignore[arg-type]

        a, b, c = element.vertices
        triangles.append((a, b, c))
        materials.append(region.material)

    return Surface(
        quantity=quantity or "",
        x=tuple(coordinate.x for coordinate in structure.coordinates),
        y=tuple(coordinate.y for coordinate in structure.coordinates),
        triangles=tuple(triangles),
        values=tuple(values),
        materials=tuple(materials),
    )
