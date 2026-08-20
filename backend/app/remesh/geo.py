"""gmsh 입력(`.geo`) 만들기.

경계와 계면을 **선으로 고정**하고 영역마다 면을 만든다. 선분이 직선이므로
gmsh 가 경계에 점을 더 넣어도 형상은 변하지 않는다. 안쪽만 새로 짜인다.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import median

from app.remesh.geometry import constrained_segments, region_loops
from app.str_parser.models import Structure

#: 경계 점의 목표 크기를 이 범위로 자른다.
#:
#: 식각이 남긴 sub-nm 점(실측: 0.16 nm 간격)을 그대로 크기로 쓰면 그 주변이
#: 통째로 그 해상도로 채워져 삼각형이 폭발한다. 그 점들은 제약으로 남지만
#: **크기 지시는 하한으로 자른다** — 1 nm 는 etch_elem.c 의 SNAP_DIST 와 같은
#: 값이고, 실리콘 격자상수의 두 배쯤이다.
_MIN_SIZE = 1.0e-3
#: 위쪽은 경계 간격 분포의 이 분위수로 정한다. 안쪽이 지나치게 성겨지지 않게.
_MAX_QUANTILE = 0.9


@dataclass(frozen=True, slots=True)
class Surface:
    region_id: int
    #: 첫 루프가 바깥, 나머지는 구멍. 각 원소는 부호 있는 선 번호 목록이다.
    loops: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class GeoModel:
    #: (x, y, 목표크기). gmsh Point 번호는 1-based 순서.
    points: tuple[tuple[float, float, float], ...]
    #: (시작점, 끝점) — 1-based Point 번호.
    lines: tuple[tuple[int, int], ...]
    surfaces: tuple[Surface, ...]
    #: gmsh 점 번호 → 원본 좌표 인덱스. 값 이송이 이걸로 옛 점을 찾는다.
    origin: tuple[int, ...]

    def to_text(self) -> str:
        out = ["// 자동 생성 — app/remesh/geo.py", "SetFactory(\"Built-in\");"]
        for i, (x, y, size) in enumerate(self.points, start=1):
            out.append(f"Point({i}) = {{{x:.10g}, {y:.10g}, 0, {size:.10g}}};")
        for i, (a, b) in enumerate(self.lines, start=1):
            out.append(f"Line({i}) = {{{a}, {b}}};")

        loop_id = 0
        by_region: dict[int, list[int]] = {}
        for surface_id, surface in enumerate(self.surfaces, start=1):
            ids = []
            for loop in surface.loops:
                loop_id += 1
                out.append(
                    f"Curve Loop({loop_id}) = {{{', '.join(str(r) for r in loop)}}};"
                )
                ids.append(loop_id)
            out.append(
                f"Plane Surface({surface_id}) = {{{', '.join(str(i) for i in ids)}}};"
            )
            by_region.setdefault(surface.region_id, []).append(surface_id)

        # 어느 삼각형이 어느 영역인지 알아야 .str 로 되쓸 수 있다.
        # 같은 태그를 두 번 선언하면 gmsh 가 거부하므로 영역마다 한 번만 낸다.
        for region, ids in sorted(by_region.items()):
            out.append(
                f"Physical Surface({region}) = {{{', '.join(str(i) for i in ids)}}};"
            )
        return "\n".join(out) + "\n"


def build_geo(structure: Structure) -> GeoModel:
    segments = constrained_segments(structure)
    loops = region_loops(structure)
    coords = structure.coordinates

    used = sorted({i for s in segments for i in (s.a, s.b)})
    index = {origin: n for n, origin in enumerate(used, start=1)}

    sizes = _sizes(segments, coords, used)
    points = tuple(
        (coords[i].x, coords[i].y, sizes[i]) for i in used
    )

    # 선은 제약 변마다 하나. 루프가 부호로 방향을 나타낸다.
    line_of: dict[tuple[int, int], int] = {}
    lines: list[tuple[int, int]] = []
    for s in segments:
        lines.append((index[s.a], index[s.b]))
        line_of[(s.a, s.b)] = len(lines)

    # 한 영역이 떨어진 조각 여러 개일 수 있다. 조각마다 면을 하나씩 만든다.
    surfaces = tuple(
        Surface(region, group)
        for region, region_loop_list in sorted(loops.items())
        for group in _oriented_loops(region_loop_list, line_of, coords)
    )

    return GeoModel(points, tuple(lines), surfaces, tuple(used))


def _sizes(segments, coords, used) -> dict[int, float]:
    """점마다의 목표 크기.

    그 점에 붙은 제약 변 길이의 **중앙값**을 쓴다. 최솟값을 쓰면 sub-nm 변
    하나가 주변 전체를 그 해상도로 끌어내린다.
    """
    incident: dict[int, list[float]] = {}
    lengths: list[float] = []
    for s in segments:
        length = hypot(coords[s.a].x - coords[s.b].x, coords[s.a].y - coords[s.b].y)
        lengths.append(length)
        incident.setdefault(s.a, []).append(length)
        incident.setdefault(s.b, []).append(length)

    lengths.sort()
    ceiling = lengths[int(len(lengths) * _MAX_QUANTILE)] if lengths else _MIN_SIZE
    ceiling = max(ceiling, _MIN_SIZE)

    return {
        i: min(max(median(incident.get(i, [ceiling])), _MIN_SIZE), ceiling)
        for i in used
    }


def _refs(loop, line_of) -> tuple[int, ...]:
    """루프를 부호 있는 선 번호로. 반대 방향으로 저장된 변은 음수로 참조한다."""
    out = []
    for i in range(len(loop) - 1):
        a, b = loop[i], loop[i + 1]
        out.append(line_of[(a, b)] if (a, b) in line_of else -line_of[(b, a)])
    return tuple(out)


def _inside(point, polygon) -> bool:
    """점이 다각형 안인가. 광선 교차 세기."""
    x, y = point
    inside = False
    for i in range(len(polygon)):
        ax, ay = polygon[i - 1]
        bx, by = polygon[i]
        if (ay > y) != (by > y):
            cut = ax + (y - ay) * (bx - ax) / (by - ay)
            if cut > x:
                inside = not inside
    return inside


def nest_loops(polygons: list[list[tuple[float, float]]]) -> list[list[int]]:
    """루프들을 면 단위로 묶는다.

    한 영역이 루프를 여럿 가질 때, 그것이 **구멍인지 떨어진 조각인지** 갈라야
    한다. 실측: 질화막 마스크 두 개, 게이트 두 개, 스페이서 네 개가 전부 떨어진
    조각이었다. 전부 구멍으로 치면 그 자리가 메시에서 빠지고, 계면 건너편이
    비어 경계 조건 복원이 실패한다.

    Returns:
        면마다 `[바깥 루프, 구멍...]` 의 인덱스 목록.
    """
    depth = []
    parents: list[int | None] = []
    for i, polygon in enumerate(polygons):
        containers = [
            j
            for j, other in enumerate(polygons)
            if j != i and _inside(polygon[0], other)
        ]
        depth.append(len(containers))
        # 바로 위 부모는 그중 가장 깊은 것.
        parents.append(max(containers, key=lambda j: len(
            [k for k in range(len(polygons)) if k != j and _inside(polygons[j][0], polygons[k])]
        )) if containers else None)

    groups: list[list[int]] = []
    index_of: dict[int, int] = {}
    for i in range(len(polygons)):
        if depth[i] % 2 == 0:          # 짝수 깊이 = 채우는 면
            index_of[i] = len(groups)
            groups.append([i])
    for i in range(len(polygons)):
        if depth[i] % 2 == 1:          # 홀수 깊이 = 부모의 구멍
            parent = parents[i]
            if parent is not None and parent in index_of:
                groups[index_of[parent]].append(i)
    return groups


def _oriented_loops(loops, line_of, coords) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """영역의 루프들을 면 단위로 묶어 돌려준다."""
    polygons = [[(coords[i].x, coords[i].y) for i in loop[:-1]] for loop in loops]
    return tuple(
        tuple(_refs(loops[i], line_of) for i in group)
        for group in nest_loops(polygons)
    )
