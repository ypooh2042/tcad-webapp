"""옛 메시의 물성값을 새 메시로 옮긴다.

새 점이 놓인 옛 삼각형을 찾아 세 노드 값을 무게중심 좌표로 섞는다(P1 보간).

**물질을 맞춰야 한다.** 계면 점은 물질마다 값이 다르다(`models.py` 에 실측
사례가 적혀 있다). 물질을 무시하고 가까운 값을 집으면 계면에서 농도가 튄다.

**선량은 보존되지 않는다.** P1 보간은 값을 옮길 뿐 적분량을 지키지 않는다.
얼마나 어긋나는지는 호출부가 재서 보고한다.
"""

from __future__ import annotations

from math import floor
from typing import Sequence

from app.str_parser.models import Structure

#: 무게중심 좌표가 이만큼 음수여도 안에 있는 것으로 본다. 경계 위의 점이
#: 반올림 때문에 어느 삼각형에도 안 들어가는 것을 막는다.
_INSIDE_TOL = 1.0e-9

#: 격자 색인의 한 변 목표 칸 수. 삼각형 수에 맞춰 조정된다.
_TARGET_BUCKET = 2.0


class Sampler:
    """옛 구조에서 물질별로 값을 뽑아 주는 색인.

    구조가 크므로(삼각형 2 만 개, 새 점 1 만 개) 훑기로는 못 견딘다.
    균일 격자 버킷으로 후보를 줄인다.
    """

    def __init__(self, structure: Structure) -> None:
        self._s = structure
        self._material_of = {r.id: r.material_id for r in structure.regions}

        coords = structure.coordinates
        xs = [c.x for c in coords]
        ys = [c.y for c in coords]
        self._x0, self._x1 = min(xs), max(xs)
        self._y0, self._y1 = min(ys), max(ys)

        side = max(1, int((len(structure.elements) / _TARGET_BUCKET) ** 0.5))
        self._n = side
        self._dx = max((self._x1 - self._x0) / side, 1e-30)
        self._dy = max((self._y1 - self._y0) / side, 1e-30)

        # 물질마다 따로 담는다. 물질이 다르면 후보로 볼 이유가 없다.
        self._buckets: dict[tuple[int, int, int], list[int]] = {}
        for index, element in enumerate(structure.elements):
            material = self._material_of.get(element.region_id)
            if material is None:
                continue
            px = [coords[i].x for i in element.vertices]
            py = [coords[i].y for i in element.vertices]
            for gx in range(self._cell_x(min(px)), self._cell_x(max(px)) + 1):
                for gy in range(self._cell_y(min(py)), self._cell_y(max(py)) + 1):
                    self._buckets.setdefault((material, gx, gy), []).append(index)

    def at(self, x: float, y: float, material: int) -> tuple[float, ...] | None:
        """(x, y) 에서 그 물질의 값. 그 물질이 거기 없으면 None."""
        candidates = self._buckets.get(
            (material, self._cell_x(x), self._cell_y(y))
        )
        if not candidates:
            return None

        coords = self._s.coordinates
        for index in candidates:
            element = self._s.elements[index]
            a, b, c = (coords[i] for i in element.vertices)
            weights = _barycentric(x, y, a, b, c)
            if weights is None:
                continue
            return self._blend(element.vertices, material, weights)
        return None

    def _blend(
        self, vertices: Sequence[int], material: int, weights: tuple[float, float, float]
    ) -> tuple[float, ...] | None:
        rows = []
        for point in vertices:
            try:
                rows.append(self._s.solution_at(point, material))
            except KeyError:
                # 그 물질 쪽 값이 없는 꼭짓점. 이 삼각형으로는 섞을 수 없다.
                return None
        return tuple(
            sum(w * row.values[i] for w, row in zip(weights, rows))
            for i in range(len(rows[0].values))
        )

    def _cell_x(self, x: float) -> int:
        return min(self._n - 1, max(0, int(floor((x - self._x0) / self._dx))))

    def _cell_y(self, y: float) -> int:
        return min(self._n - 1, max(0, int(floor((y - self._y0) / self._dy))))


def _barycentric(x, y, a, b, c) -> tuple[float, float, float] | None:
    den = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)
    if den == 0:
        return None
    wa = ((b.y - c.y) * (x - c.x) + (c.x - b.x) * (y - c.y)) / den
    wb = ((c.y - a.y) * (x - c.x) + (a.x - c.x) * (y - c.y)) / den
    wc = 1.0 - wa - wb
    if wa < -_INSIDE_TOL or wb < -_INSIDE_TOL or wc < -_INSIDE_TOL:
        return None
    return (wa, wb, wc)
