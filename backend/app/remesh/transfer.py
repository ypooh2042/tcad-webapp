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
        # (점, 물질) → 값 튜플. solution_at 은 매번 dict 를 거치는데 여기서는
        # 점마다 세 번씩 부르게 되므로 미리 펼쳐 둔다.
        self._values = {
            (row.coordinate_index, row.material_id): row.values
            for row in structure.solutions
        }

        coords = structure.coordinates
        # 좌표를 평평한 리스트로 들고 있는다. 점마다 `.x`/`.y` 속성을 다시
        # 들추면 그것만으로 수백만 번이 된다.
        self._px = [c.x for c in coords]
        self._py = [c.y for c in coords]
        xs, ys = self._px, self._py
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

    def at(
        self, x: float, y: float, material: int, reach: float = 0.0
    ) -> tuple[float, ...] | None:
        """(x, y) 에서 그 물질의 값. 그 물질이 거기 없으면 None.

        Args:
            reach: 삼각형 안에 들어가지 않을 때 이 거리까지는 가장 가까운
                삼각형으로 물러선다. 경계를 단순화하면 새 점이 옛 물질에서
                허용오차만큼 벗어나기 때문이다. 0 이면 물러서지 않는다.
        """
        px, py = self._px, self._py
        candidates = self._buckets.get((material, self._cell_x(x), self._cell_y(y)))

        for index in candidates or ():
            v = self._s.elements[index].vertices
            i, j, k = v
            weights = _barycentric(
                x, y, px[i], py[i], px[j], py[j], px[k], py[k]
            )
            if weights is not None:
                blended = self._blend(v, material, weights)
                if blended is not None:
                    return blended

        if reach <= 0:
            return None
        return self._nearest(x, y, material, reach)

    def _nearest(self, x, y, material, reach) -> tuple[float, ...] | None:
        """가장 가까운 삼각형에 투영해 값을 뽑는다. 이웃 칸까지만 본다."""
        px, py = self._px, self._py
        cx, cy = self._cell_x(x), self._cell_y(y)
        best = None
        best_distance = reach
        for gx in range(cx - 1, cx + 2):
            for gy in range(cy - 1, cy + 2):
                for index in self._buckets.get((material, gx, gy), ()):
                    v = self._s.elements[index].vertices
                    for i in range(3):
                        a, b = v[i], v[(i + 1) % 3]
                        d = _point_to_segment(
                            (x, y), (px[a], py[a]), (px[b], py[b])
                        )
                        if d < best_distance:
                            best_distance, best = d, v
        if best is None:
            return None
        i, j, k = best
        weights = _barycentric(
            x, y, px[i], py[i], px[j], py[j], px[k], py[k], clamp=True
        )
        return self._blend(best, material, weights) if weights else None

    def _blend(
        self, vertices: Sequence[int], material: int, weights: tuple[float, float, float]
    ) -> tuple[float, ...] | None:
        """세 꼭짓점 값을 무게중심 좌표로 섞는다.

        값 배열을 먼저 지역 변수로 꺼내고 한 번만 훑는다. 종마다 제너레이터를
        새로 만들면 점 8 만 개 × 종 14 개 = 100 만 번이 되어 그것만으로 이송
        시간의 절반을 먹는다(실측).
        """
        rows = self._values
        try:
            va = rows[(vertices[0], material)]
            vb = rows[(vertices[1], material)]
            vc = rows[(vertices[2], material)]
        except KeyError:
            # 그 물질 쪽 값이 없는 꼭짓점. 이 삼각형으로는 섞을 수 없다.
            return None
        wa, wb, wc = weights
        return tuple(wa * a + wb * b + wc * c for a, b, c in zip(va, vb, vc))

    def _cell_x(self, x: float) -> int:
        return min(self._n - 1, max(0, int(floor((x - self._x0) / self._dx))))

    def _cell_y(self, y: float) -> int:
        return min(self._n - 1, max(0, int(floor((y - self._y0) / self._dy))))


def _barycentric(
    x, y, ax, ay, bx, by, cx, cy, clamp: bool = False
) -> tuple[float, float, float] | None:
    den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if den == 0:
        return None
    wa = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / den
    wb = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / den
    wc = 1.0 - wa - wb
    if clamp:
        # 삼각형 밖이면 안으로 눌러 담는다. 값이 바깥으로 발산하지 않게 한다.
        wa, wb, wc = max(wa, 0.0), max(wb, 0.0), max(wc, 0.0)
        total = wa + wb + wc
        return (wa / total, wb / total, wc / total) if total > 0 else None
    if wa < -_INSIDE_TOL or wb < -_INSIDE_TOL or wc < -_INSIDE_TOL:
        return None
    return (wa, wb, wc)


def _point_to_segment(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    if length == 0:
        return ((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length))
    return ((p[0] - (a[0] + t * dx)) ** 2 + (p[1] - (a[1] + t * dy)) ** 2) ** 0.5
