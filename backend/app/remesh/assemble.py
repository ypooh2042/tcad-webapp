"""새 메시를 `.str` 구조로 조립한다.

두 가지가 까다롭다.

    이웃·경계조건 — SUPREM 은 경계 조건을 `t` 라인의 음수 이웃 필드에만
        담는다(`'b'` 레코드는 리더가 무시한다). 새 경계 변은 옛 경계 변 위에
        놓이므로 코드를 물려받는다. 잃으면 노출면·뒷면이 사라진다.

    노드 모델 — 노드는 (점, 물질) 하나씩이다. 계면 점은 인접 물질 수만큼
        여러 줄이 나온다.
"""

from __future__ import annotations

from math import hypot

from app.remesh.geometry import constrained_segments
from app.str_parser.boundary import BoundaryCondition
from app.str_parser.materials import AMBIENT_MATERIAL_ID
from app.remesh.msh import Mesh
from app.remesh.transfer import Sampler
from app.str_parser.models import Coordinate, Element, NodeSolution, Structure

_VERTICES = 3

#: 새 경계 변이 옛 경계에서 이만큼까지 떨어져 있어도 같은 경계로 본다.
#:
#: 경계를 그대로 보존하면 0 이어도 되지만, 단순화를 켜면 새 변이 모서리를
#: 가로지르는 현이라 허용오차만큼 떨어진다. 그래서 호출부가 쓴 단순화
#: 허용오차를 받아 그 몇 배까지 허용한다.
_ON_SEGMENT = 1.0e-9
_SIMPLIFY_MARGIN = 4.0


def assemble(old: Structure, mesh: Mesh, boundary_tolerance: float = 0.0) -> Structure:
    """옛 구조의 물성값을 새 메시에 실어 새 구조를 만든다.

    Raises:
        ValueError: 새 점에 값을 실을 수 없을 때. 조용히 0 을 넣으면 없던
            층이 생기거나 도핑이 사라진다.
    """
    material_of = {r.id: r.material_id for r in old.regions}

    coordinates = tuple(
        Coordinate(id=i + 1, x=x, y=y) for i, (x, y) in enumerate(mesh.points)
    )
    reach = max(_ON_SEGMENT, boundary_tolerance * _SIMPLIFY_MARGIN)
    elements = _elements(old, mesh, reach)
    solutions = _solutions(old, mesh, material_of, coordinates, elements, reach)

    return Structure(
        version=old.version,
        dimension=old.dimension,
        vertices_per_element=old.vertices_per_element,
        neighbors_per_element=old.neighbors_per_element,
        coordinates=coordinates,
        regions=old.regions,
        elements=elements,
        solutions=solutions,
        table=old.table,
        temperature_k=old.temperature_k,
        warnings=old.warnings,
        _solution_index={(s.coordinate_index, s.material_id): s for s in solutions},
    )


def _elements(old: Structure, mesh: Mesh, reach: float) -> tuple[Element, ...]:
    """삼각형마다 이웃을 잇고, 바깥 변에는 옛 경계 조건을 물려준다."""
    # 변 → 그 변을 가진 (삼각형, 맞은편 정점) 목록.
    owner: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for t, tri in enumerate(mesh.triangles):
        v = tri.vertices
        for i in range(_VERTICES):
            a, b = v[(i + 1) % _VERTICES], v[(i + 2) % _VERTICES]
            owner.setdefault((min(a, b), max(a, b)), []).append((t, i))

    outer = tuple(s for s in constrained_segments(old) if s.is_outer)
    old_coords = old.coordinates

    elements: list[Element] = []
    for t, tri in enumerate(mesh.triangles):
        v = tri.vertices
        neighbors: list[int] = []
        for i in range(_VERTICES):
            a, b = v[(i + 1) % _VERTICES], v[(i + 2) % _VERTICES]
            sharers = owner[(min(a, b), max(a, b))]
            other = [s for s in sharers if s[0] != t]
            if other:
                neighbors.append(other[0][0])
                continue
            mid = (
                (mesh.points[a][0] + mesh.points[b][0]) / 2,
                (mesh.points[a][1] + mesh.points[b][1]) / 2,
            )
            neighbors.append(_boundary_code(mid, outer, old_coords, reach))

        elements.append(
            Element(
                id=t + 1,
                region_id=tri.region_id,
                vertices=tuple(v),
                neighbors=tuple(neighbors),
                # father/offspr. 원본 파일이 전부 -1 -1 이다.
                extra=(-1, -1),
            )
        )
    return tuple(elements)


def _boundary_code(mid, outer, coords, reach: float) -> int:
    """바깥 변의 경계 조건. 옛 경계 선분 중 가장 가까운 것에서 가져온다."""
    best = None
    best_distance = reach
    for segment in outer:
        a, b = coords[segment.a], coords[segment.b]
        distance = _point_to_segment(mid, (a.x, a.y), (b.x, b.y))
        if distance <= best_distance:
            best_distance = distance
            best = segment
    if best is None:
        raise ValueError(
            f"바깥 변 {mid} 이 어느 옛 경계에도 놓여 있지 않습니다"
        )
    return best.bc


def _point_to_segment(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    if length == 0:
        return hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length))
    return hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


#: ambient 노드가 붙는 경계. 노출면과 뒷면은 바깥과 접하지만 REFLECT 는
#: 대칭면이라 실제 표면이 아니다. 실측으로 확인했다 — 픽스처에서
#: ambient 노드 수가 EXPOSED + BACKSIDE 점 수와 정확히 같다(86+35=121).
_AMBIENT_BOUNDARIES = frozenset(
    {BoundaryCondition.EXPOSED.value, BoundaryCondition.BACKSIDE.value}
)


def _solutions(old, mesh, material_of, coordinates, elements, reach) -> tuple[NodeSolution, ...]:
    """점마다, 그 점에 닿는 물질마다 한 줄씩 값을 만든다.

    바깥과 접하는 점에는 ambient(물질 0) 줄이 하나 더 붙는다. 영역 표에는
    없고 `n` 라인에만 나오는 물질이라 삼각형만 봐서는 알 수 없다.
    """
    touching: dict[int, set[int]] = {}
    for tri in mesh.triangles:
        material = material_of[tri.region_id]
        for point in tri.vertices:
            touching.setdefault(point, set()).add(material)

    ambient = _ambient_values(old)
    if ambient is not None:
        for element in elements:
            v = element.vertices
            for i, code in enumerate(element.neighbors):
                if code in _AMBIENT_BOUNDARIES:
                    for point in (v[(i + 1) % _VERTICES], v[(i + 2) % _VERTICES]):
                        touching.setdefault(point, set()).add(AMBIENT_MATERIAL_ID)

    sampler = Sampler(old)
    names = old.table
    out: list[NodeSolution] = []
    for point in sorted(touching):
        x, y = mesh.points[point]
        for material in sorted(touching[point]):
            if material == AMBIENT_MATERIAL_ID:
                out.append(
                    NodeSolution(
                        coordinate_index=point,
                        material_id=AMBIENT_MATERIAL_ID,
                        material="ambient",
                        values=ambient,
                        table=names,
                    )
                )
                continue
            values = sampler.at(x, y, material, reach=reach)
            if values is None:
                raise ValueError(
                    f"점 {point} ({x:g}, {y:g}) 의 물질 {material} 값을 "
                    "옛 메시에서 찾지 못했습니다"
                )
            out.append(
                NodeSolution(
                    coordinate_index=point,
                    material_id=material,
                    material=_material_name(old, material),
                    values=values,
                    table=names,
                )
            )
    return tuple(out)


def _ambient_values(old: Structure) -> tuple[float, ...] | None:
    """ambient 노드에 넣을 값. 원본에서 그대로 가져온다.

    실측: 한 구조 안의 ambient 노드는 값이 전부 같다(자리표시자다). 그래서
    아무 하나를 집어도 된다.
    """
    for node in old.solutions:
        if node.material_id == AMBIENT_MATERIAL_ID:
            return node.values
    return None


def _material_name(old: Structure, material_id: int) -> str:
    for region in old.regions:
        if region.material_id == material_id:
            return region.material
    return "unknown"
