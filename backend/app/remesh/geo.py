"""gmsh 입력(`.geo`) 만들기.

경계와 계면을 **선으로 고정**하고 영역마다 면을 만든다. 선분이 직선이므로
gmsh 가 경계에 점을 더 넣어도 형상은 변하지 않는다. 안쪽만 새로 짜인다.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import median

from app.remesh.geometry import Segment, constrained_segments, region_loops
from app.remesh.simplify import simplify_boundary
from app.remesh.sizefield import node_sizes
from app.str_parser.models import Structure

#: 기울기 세분화 하한을 경계 해상도의 몇 분의 일로 잡을지.
_GRADIENT_FLOOR_RATIO = 10.0

#: 배경 크기장을 담을 파일 이름. `.geo` 가 이 이름으로 Merge 한다.
BACKGROUND_FILE = "sizes.pos"

#: 경계 점의 목표 크기 하한. **단위는 µm** — `.str` 좌표가 µm 다.
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


#: 경계층에서 안쪽 크기로 넘어가는 구간. 경계 해상도의 배수로 잡는다.
#: 좁으면 전이가 급해 품질이 떨어지고, 넓으면 안쪽까지 촘촘해진다.
_GRADE_NEAR = 2.0
_GRADE_FAR = 20.0


@dataclass(frozen=True, slots=True)
class GeoModel:
    #: (x, y, 목표크기). gmsh Point 번호는 1-based 순서.
    points: tuple[tuple[float, float, float], ...]
    #: (시작점, 끝점) — 1-based Point 번호.
    lines: tuple[tuple[int, int], ...]
    surfaces: tuple[Surface, ...]
    #: gmsh 점 번호 → 원본 좌표 인덱스. 값 이송이 이걸로 옛 점을 찾는다.
    origin: tuple[int, ...]
    #: 경계에서 먼 곳의 목표 크기. 옛 메시의 안쪽 밀도를 그대로 노린다.
    interior_size: float
    #: 경계 근처의 목표 크기.
    boundary_size: float
    #: 도핑 기울기에서 나온 배경 크기장. gmsh 가 읽을 `.pos` 텍스트다.
    background: str

    def to_text(self) -> str:
        out = [
            "// 자동 생성 — app/remesh/geo.py",
            "SetFactory(\"Built-in\");",
            # 경계 크기를 안쪽으로 **퍼뜨리게 둔다**(기본값). 막아 봤더니
            # 전이가 급해져 품질이 오히려 나빠졌다 — 실측으로 최소각이
            # 25.57° 에서 7.79° 로 떨어졌다. 점은 1.6 배 그대로였다.
            # 아래 Threshold 필드가 **먼 곳의 상한**만 잡아 준다.
            "Mesh.MeshSizeExtendFromBoundary = 1;",
            "Mesh.MeshSizeFromPoints = 1;",
            "Mesh.MeshSizeFromCurvature = 0;",
        ]
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

        # 경계에서 멀어질수록 성기게. 경계층은 경계 해상도로, 안쪽은 옛 메시의
        # 안쪽 밀도로 간다 — 밀도는 그대로 두고 품질만 올리는 것이 목적이다.
        curves = ", ".join(str(i) for i in range(1, len(self.lines) + 1))
        out += [
            "Field[1] = Distance;",
            f"Field[1].CurvesList = {{{curves}}};",
            "Field[2] = Threshold;",
            "Field[2].InField = 1;",
            f"Field[2].SizeMin = {self.boundary_size:.10g};",
            f"Field[2].SizeMax = {max(self.interior_size, self.boundary_size):.10g};",
            f"Field[2].DistMin = {self.boundary_size * _GRADE_NEAR:.10g};",
            f"Field[2].DistMax = {self.boundary_size * _GRADE_FAR:.10g};",
            # 도핑이 가파른 자리는 더 촘촘하게. 기하만 보고 성기게 만들면
            # 접합이 뭉개진다(실측: 비소 총선량 13.6% 오차).
            f'Merge "{BACKGROUND_FILE}";',
            "Field[3] = PostView;",
            "Field[3].ViewIndex = 0;",
            "Field[4] = Min;",
            "Field[4].FieldsList = {2, 3};",
            "Background Field = 4;",
        ]
        return "\n".join(out) + "\n"


def build_geo(structure: Structure, simplify_tolerance: float = 0.0) -> GeoModel:
    """제약 기하를 gmsh 입력으로.

    Args:
        simplify_tolerance: 경계에서 이 거리 이내로만 움직이는 점은 걷어낸다.
            0 이면 경계를 글자 그대로 보존한다.
    """
    segments = constrained_segments(structure)
    loops = region_loops(structure)
    coords = structure.coordinates

    keep = simplify_boundary(structure, simplify_tolerance)
    loops = {r: [_thin(lp, keep) for lp in lps] for r, lps in loops.items()}
    segments = tuple(
        s for s in segments if s.a in keep and s.b in keep
    ) if simplify_tolerance > 0 else segments
    if simplify_tolerance > 0:
        segments = _relink(loops, structure)

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

    boundary_size = _boundary_size(segments, coords)
    interior_size = _interior_size(structure, segments)
    return GeoModel(
        points,
        tuple(lines),
        surfaces,
        tuple(used),
        interior_size=interior_size,
        boundary_size=boundary_size,
        # 기울기 세분화의 하한.
        #
        # 경계 크기를 하한으로 주면 하한과 상한이 같아져 세분화가 통째로
        # 막힌다(실측: 배경장을 넣었는데 결과가 한 점도 안 바뀌었다).
        # 반대로 1 nm 까지 열어 주면 주입 프로파일 전체가 하한까지 쪼개져
        # 점이 65 배로 폭발한다(실측: 8,703 → 566,774).
        #
        # 그래서 **구조 자체의 척도**에 묶는다 — 경계 해상도의 1/10. 접합은
        # 보통 수십~수백 nm 깊이이므로 그 1/10 이면 넉넉히 분해된다.
        background=_background(
            structure,
            floor=max(_MIN_SIZE, boundary_size / _GRADIENT_FLOOR_RATIO),
            ceiling=max(interior_size, boundary_size),
        ),
    )


def _background(structure, floor: float, ceiling: float) -> str:
    """도핑 기울기에서 나온 크기장을 gmsh `.pos` 뷰로.

    삼각형마다 세 꼭짓점의 목표 크기를 적는다(`ST`). gmsh 가 그 사이를
    보간해 배경 크기장으로 쓴다.
    """
    sizes = node_sizes(structure, floor=floor, ceiling=ceiling)
    coords = structure.coordinates
    rows = ['View "sizes" {']
    for element in structure.elements:
        p = [coords[i] for i in element.vertices]
        v = [sizes[i] for i in element.vertices]
        rows.append(
            "ST(%.10g,%.10g,0,%.10g,%.10g,0,%.10g,%.10g,0){%.10g,%.10g,%.10g};"
            % (p[0].x, p[0].y, p[1].x, p[1].y, p[2].x, p[2].y, v[0], v[1], v[2])
        )
    rows.append("};")
    return "\n".join(rows) + "\n"


def _boundary_size(segments, coords) -> float:
    """경계 근처의 목표 크기 — 제약 변 길이의 중앙값."""
    lengths = [
        hypot(coords[s.a].x - coords[s.b].x, coords[s.a].y - coords[s.b].y)
        for s in segments
    ]
    return max(median(lengths), _MIN_SIZE) if lengths else _MIN_SIZE


def _interior_size(structure, segments) -> float:
    """안쪽의 목표 크기 — 옛 메시의 **안쪽** 변 길이 중앙값.

    옛 밀도를 그대로 노린다. 안쪽 변이 하나도 없는 성긴 구조에서는 경계 크기로
    물러선다 — 0 을 크기로 주면 gmsh 가 멈춘다.
    """
    fixed = {(min(s.a, s.b), max(s.a, s.b)) for s in segments}
    coords = structure.coordinates
    seen: set[tuple[int, int]] = set()
    lengths: list[float] = []
    for element in structure.elements:
        v = element.vertices
        for i in range(len(v)):
            key = (min(v[i], v[(i + 1) % len(v)]), max(v[i], v[(i + 1) % len(v)]))
            if key in fixed or key in seen:
                continue
            seen.add(key)
            lengths.append(
                hypot(
                    coords[key[0]].x - coords[key[1]].x,
                    coords[key[0]].y - coords[key[1]].y,
                )
            )
    if not lengths:
        return _boundary_size(segments, coords)
    return median(lengths)


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


def _thin(loop: list[int], keep: set[int]) -> list[int]:
    """루프에서 남길 점만. 닫힘은 유지한다."""
    thinned = [i for i in loop[:-1] if i in keep]
    return thinned + [thinned[0]] if thinned else loop


def _relink(loops, structure) -> tuple[Segment, ...]:
    """단순화된 루프에서 제약 변을 다시 만든다.

    점을 걷어내면 이웃이 바뀌므로 원래 변 목록을 그대로 쓸 수 없다. 루프가
    곧 새 경계이므로 거기서 다시 잇는다. 변의 성격(양쪽 영역, 경계 조건)은
    원래 변에서 물려받는다 — 같은 자리에 놓여 있기 때문이다.
    """
    original = {
        (min(s.a, s.b), max(s.a, s.b)): s for s in constrained_segments(structure)
    }
    # 점 → 그 점에 붙어 있던 변들. 새 변의 성격을 여기서 고른다.
    at: dict[int, list[Segment]] = {}
    for s in original.values():
        at.setdefault(s.a, []).append(s)
        at.setdefault(s.b, []).append(s)

    out: dict[tuple[int, int], Segment] = {}
    for region, region_loops_ in loops.items():
        for loop in region_loops_:
            for i in range(len(loop) - 1):
                a, b = loop[i], loop[i + 1]
                key = (min(a, b), max(a, b))
                if key in out:
                    continue
                kept = original.get(key)
                if kept is None:
                    # 걷어낸 점들을 건너뛴 새 변. 양끝이 공유하는 성격을 쓴다.
                    shared = [
                        s
                        for s in at.get(a, [])
                        if any(
                            (s.left_region, s.right_region, s.bc)
                            == (t.left_region, t.right_region, t.bc)
                            for t in at.get(b, [])
                        )
                    ]
                    template = shared[0] if shared else at[a][0]
                    kept = Segment(
                        a, b, template.left_region, template.right_region, template.bc
                    )
                out[key] = Segment(a, b, kept.left_region, kept.right_region, kept.bc)
    return tuple(out.values())
