"""`.str` 구조를 DevSim 장치 메쉬로 옮긴다.

**파일을 거치지 않는다.** `devsim.create_gmsh_mesh` 는 `file=` 대신
`coordinates=/elements=/physical_names=` 로 배열을 그대로 받는다(실측 확인).
그래서 gmsh 바이너리도, `.msh` 쓰기도 필요 없다.

    coordinates    [x0,y0,z0, x1,y1,z1, ...]
    elements       [타입, physical 인덱스(0-based), 노드...] 가 이어붙은 평평한 리스트
                   타입 1 = 변(노드 2), 2 = 삼각형(노드 3)
    physical_names 영역·계면·접촉 이름

단위계가 다르다. SUPREM 은 µm 이고 y 가 깊이(아래가 +)인데, DevSim 은 cm 이고
보통의 y 축을 쓴다(`simple_physics.py` 의 `eps_0 = 8.85e-14 F/cm`). 그래서
좌표를 ×1e-4 하고 y 부호를 뒤집는다. 뒤집으면 삼각형 방향이 반대가 되므로
정점 순서도 함께 바로잡는다 — 안 하면 넓이가 음수인 요소가 나온다.
농도는 이미 cm⁻³ 라 손대지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from app.devsim.electrodes import (
    INSULATORS,
    SEMICONDUCTORS,
    ContactKind,
    Electrode,
    GateModel,
)
from app.remesh.geometry import constrained_segments
from app.str_parser.models import Structure

#: µm → cm.
UM_TO_CM = 1.0e-4

#: `elements` 배열의 타입 코드.
EDGE = 1
TRIANGLE = 2

#: SUPREM 재질 → DevSim 재질 이름. DevSim 쪽은 물성 파라미터를 걸 때의 꼬리표다.
DEVSIM_MATERIAL = {
    "silicon": "Silicon",
    "poly": "Silicon",
    "gaas": "GaAs",
    "oxide": "Oxide",
    "nitride": "Nitride",
    "oxynitride": "Oxide",
}


@dataclass(frozen=True, slots=True)
class RegionSpec:
    name: str
    region_id: int
    #: SUPREM 재질 이름.
    material: str
    devsim_material: str

    @property
    def is_semiconductor(self) -> bool:
        return self.material in SEMICONDUCTORS


@dataclass(frozen=True, slots=True)
class InterfaceSpec:
    name: str
    region0: str
    region1: str


@dataclass(frozen=True, slots=True)
class ContactSpec:
    #: DevSim 접촉 이름. 전극 하나가 여러 영역에 닿으면 영역마다 하나씩 생긴다.
    name: str
    #: 바이어스를 공유하는 단위. 여러 접촉이 같은 전극을 가리킬 수 있다.
    electrode: str
    region: str
    kind: ContactKind


@dataclass(frozen=True, slots=True)
class DeviceMesh:
    coordinates: tuple[float, ...]
    elements: tuple[int, ...]
    physical_names: tuple[str, ...]
    regions: tuple[RegionSpec, ...]
    interfaces: tuple[InterfaceSpec, ...]
    contacts: tuple[ContactSpec, ...]
    #: SUPREM 좌표 인덱스 → DevSim 좌표 인덱스.
    point_map: Mapping[int, int]


def iter_elements(
    elements: Sequence[int],
) -> Iterator[tuple[int, int, tuple[int, ...]]]:
    """평평한 `elements` 배열을 (타입, physical, 노드) 로 되읽는다.

    길이가 타입마다 다르므로 그냥 잘라 쓸 수 없다. 테스트와 검증에서 쓴다.
    """
    index = 0
    while index < len(elements):
        kind = elements[index]
        physical = elements[index + 1]
        count = 2 if kind == EDGE else 3
        nodes = tuple(elements[index + 2 : index + 2 + count])
        yield kind, physical, nodes
        index += 2 + count


def _region_name(region_id: int, material: str) -> str:
    return f"r{region_id}_{material}"


def _select_regions(
    structure: Structure,
    electrodes: Sequence[Electrode],
    gate_model: GateModel,
) -> tuple[RegionSpec, ...]:
    """해석에 넣을 영역을 고른다.

    - 반도체는 전부 넣는다. 단 `gate_model=CONDUCTOR` 면 poly 는 도체라 빠진다.
    - 절연체는 **반도체와 계면을 공유하는 것만** 넣는다. 어디에도 안 닿는
      절연막(예: 금속 위 덮개)은 전기적으로 하는 일이 없으면서 노드만 먹는다.
    - 접촉이 붙은 영역은 무조건 넣는다. 도체 게이트의 접촉이 산화막에 붙기
      때문에, 이 규칙이 없으면 접촉을 걸 영역이 사라진다.
    """
    conductors = gate_model.conductors()
    materials = {region.id: region.material for region in structure.regions}

    semiconductors = {
        region_id
        for region_id, material in materials.items()
        if material in SEMICONDUCTORS and material not in conductors
    }

    insulators = {
        region_id
        for region_id, material in materials.items()
        if material in INSULATORS and material not in conductors
    }
    touching = set()
    for segment in constrained_segments(structure):
        if segment.right_region is None:
            continue
        pair = (segment.left_region, segment.right_region)
        for one, other in (pair, pair[::-1]):
            if one in insulators and other in semiconductors:
                touching.add(one)

    required = {edge.region_id for electrode in electrodes for edge in electrode.edges}

    kept = sorted(semiconductors | touching | (required & insulators))
    return tuple(
        RegionSpec(
            name=_region_name(region_id, materials[region_id]),
            region_id=region_id,
            material=materials[region_id],
            devsim_material=DEVSIM_MATERIAL.get(materials[region_id], "Oxide"),
        )
        for region_id in kept
    )


def _contact_specs(
    electrodes: Sequence[Electrode], by_region: Mapping[int, RegionSpec]
) -> tuple[ContactSpec, ...]:
    specs: list[ContactSpec] = []
    for electrode in electrodes:
        grouped = electrode.edges_by_region()
        reachable = [region_id for region_id in grouped if region_id in by_region]
        for region_id in sorted(reachable):
            region = by_region[region_id]
            # 영역 하나뿐이면 전극 이름을 그대로 쓴다. 화면과 결과에 그 이름이
            # 그대로 나오는 편이 읽기 좋다.
            name = (
                electrode.name
                if len(reachable) == 1
                else f"{electrode.name}_r{region_id}"
            )
            specs.append(
                ContactSpec(
                    name=name,
                    electrode=electrode.name,
                    region=region.name,
                    kind=electrode.kind,
                )
            )
    return tuple(specs)


def build_device_mesh(
    structure: Structure,
    electrodes: Sequence[Electrode],
    *,
    gate_model: GateModel = GateModel.SEMICONDUCTOR,
) -> DeviceMesh:
    """DevSim 에 그대로 넘길 수 있는 메쉬를 만든다."""
    regions = _select_regions(structure, electrodes, gate_model)
    by_region = {region.region_id: region for region in regions}
    if not by_region:
        raise ValueError("해석할 영역이 없습니다. 반도체가 들어 있는 구조여야 합니다.")

    contacts = _contact_specs(electrodes, by_region)

    kept_elements = [
        element for element in structure.elements if element.region_id in by_region
    ]

    # 쓰는 점만 추린다. 금속을 뺐으므로 그 안쪽 점은 갈 곳이 없다.
    point_map: dict[int, int] = {}
    for element in kept_elements:
        for vertex in element.vertices:
            if vertex not in point_map:
                point_map[vertex] = len(point_map)

    coordinates: list[float] = [0.0] * (len(point_map) * 3)
    for source, target in point_map.items():
        point = structure.coordinates[source]
        coordinates[target * 3] = point.x * UM_TO_CM
        # y 부호를 뒤집는다. SUPREM 은 아래가 +y 다.
        coordinates[target * 3 + 1] = -point.y * UM_TO_CM
        coordinates[target * 3 + 2] = 0.0

    names: list[str] = []
    index_of: dict[str, int] = {}

    def physical(name: str) -> int:
        if name not in index_of:
            index_of[name] = len(names)
            names.append(name)
        return index_of[name]

    elements: list[int] = []

    for element in kept_elements:
        a, b, c = (point_map[v] for v in element.vertices)
        # y 를 뒤집었으므로 원래 방향이 뒤집힌다. 넓이가 음수면 바로잡는다.
        if _area(coordinates, a, b, c) < 0:
            b, c = c, b
        elements += [TRIANGLE, physical(by_region[element.region_id].name), a, b, c]

    interfaces: list[InterfaceSpec] = []
    seen_pairs: dict[tuple[int, int], InterfaceSpec] = {}
    for segment in constrained_segments(structure):
        if segment.right_region is None:
            continue
        left, right = segment.left_region, segment.right_region
        if left not in by_region or right not in by_region:
            continue
        key = (min(left, right), max(left, right))
        spec = seen_pairs.get(key)
        if spec is None:
            spec = InterfaceSpec(
                name=f"i_r{key[0]}_r{key[1]}",
                region0=by_region[key[0]].name,
                region1=by_region[key[1]].name,
            )
            seen_pairs[key] = spec
            interfaces.append(spec)
        elements += [
            EDGE,
            physical(spec.name),
            point_map[segment.a],
            point_map[segment.b],
        ]

    contact_of_edge = {
        (spec.electrode, spec.region): spec.name for spec in contacts
    }
    for electrode in electrodes:
        for edge in electrode.edges:
            region = by_region.get(edge.region_id)
            if region is None:
                continue
            name = contact_of_edge[(electrode.name, region.name)]
            elements += [
                EDGE,
                physical(name),
                point_map[edge.vertices[0]],
                point_map[edge.vertices[1]],
            ]

    return DeviceMesh(
        coordinates=tuple(coordinates),
        elements=tuple(elements),
        physical_names=tuple(names),
        regions=regions,
        interfaces=tuple(interfaces),
        contacts=contacts,
        point_map=point_map,
    )


def _area(coordinates: Sequence[float], a: int, b: int, c: int) -> float:
    ax, ay = coordinates[a * 3], coordinates[a * 3 + 1]
    bx, by = coordinates[b * 3], coordinates[b * 3 + 1]
    cx, cy = coordinates[c * 3], coordinates[c * 3 + 1]
    return 0.5 * ((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))
