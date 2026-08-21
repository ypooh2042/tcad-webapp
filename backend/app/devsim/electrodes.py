"""구조에서 전극을 찾아낸다.

판정 규칙은 SUPREM 원본에 이미 있다. `upstream/src/include/device.h:35`:

    a contact is a semiconductor material touching an Exposed or backside
    or anything touching aluminum

그리고 `device/contact.c:104 gen_contact()` 가 연결된 접촉 변을 flood-fill 해서
하나의 contact 으로 묶는다. **"같은 알루미늄 덩어리는 같은 전위"가 정확히 이것**
이므로 새로 발명하지 않고 그대로 옮긴다.

다만 한 군데는 일부러 좁혔다. 원본은 "반도체가 exposed/backside 에 닿으면"도
접촉으로 치는데, 그러면 노출된 실리콘 표면 전체가 전극이 되어 버린다. 여기서는
금속에서 나온 전극만 자동으로 잡고, 뒷면(backside)은 **후보로만** 내놓아
사용자가 받아들이거나 화면에서 고치게 한다.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

from app.str_parser.boundary import BoundaryCondition
from app.str_parser.models import Element, Structure

#: 전기적으로 도체로 볼 재질. poly 는 `GateModel` 에 따라 여기 들어오기도 한다.
METAL = "aluminum"

#: DevSim 이 드리프트-확산으로 풀 재질.
SEMICONDUCTORS = frozenset({"silicon", "poly", "gaas"})

#: 전위만 푸는(라플라스) 재질.
INSULATORS = frozenset({"oxide", "nitride", "oxynitride"})

#: 해석에서 아예 빼는 재질. 공정 보조재라 전기적 의미가 없다.
DISCARDED = frozenset({"photoresist", "ambient"})


class GateModel(Enum):
    """폴리 게이트를 무엇으로 볼 것인가.

    `SEMICONDUCTOR` — 도핑된 반도체 영역으로 함께 푼다. poly depletion 이 보인다.
    `CONDUCTOR`     — 이상 도체로 보고 금속과 한 덩어리로 묶는다. 접촉이 산화막에
                      붙어 DevSim 의 `CreateOxideContact` 형태가 된다. 노드가 줄고
                      수렴이 안정적이다.
    """

    SEMICONDUCTOR = "semiconductor"
    CONDUCTOR = "conductor"

    def conductors(self) -> frozenset[str]:
        if self is GateModel.CONDUCTOR:
            return frozenset({METAL, "poly"})
        return frozenset({METAL})


class ContactKind(Enum):
    """접촉이 어느 쪽 재질에 붙었는가. DevSim 에서 쓰는 방정식이 달라진다."""

    SEMICONDUCTOR = "semiconductor"
    INSULATOR = "insulator"


@dataclass(frozen=True, slots=True)
class Extent:
    """화면에 그릴 때 쓰는 범위(µm)."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclass(frozen=True, slots=True)
class ContactEdge:
    """접촉 변 하나.

    `element_id`/`region_id` 는 **접촉을 받는 쪽**, 즉 해석 대상 영역의 것이다.
    DevSim 의 `add_gmsh_contact(region=...)` 이 그 영역을 요구하기 때문에, 금속
    쪽 요소를 들고 있으면 쓸 수 없다.
    """

    element_id: int
    region_id: int
    vertices: tuple[int, int]


@dataclass(frozen=True, slots=True)
class Electrode:
    """등전위 단위 하나.

    두 가지 자리에서 쓴다.

    **자동으로 찾은 계면** — `detect_electrodes` / `backside_candidate` 가 내는
    것. 사용자가 만들어 내는 것이 아니라 구조에서 나온다. 금속 덩어리 하나가
    계면 하나이고, 뒷면 경계가 계면 하나다.

    **사용자가 묶은 전극** — `resolve.resolve_electrodes` 가 여러 계면의 변을
    합쳐 만든 것. 소자 해석이 실제로 접촉으로 거는 단위이며, 전압원 하나가
    여기에 1:1 로 붙는다.

    구조가 같아서 한 자료형을 쓴다. 합쳐도 "등전위인 변들의 묶음"이라는 뜻이
    달라지지 않는다.
    """

    name: str
    kind: ContactKind
    #: 닿은 재질들. 이름 붙일 때와 화면 설명에 쓴다.
    materials: tuple[str, ...]
    edges: tuple[ContactEdge, ...]
    extent: Extent
    #: 이 계면이 어디서 나왔는지. 화면이 금속 접촉과 뒷면을 구분해 보여준다.
    origin: str = "metal"

    def edges_by_region(self) -> dict[int, tuple[ContactEdge, ...]]:
        """영역별로 나눈다. DevSim 접촉은 영역 하나에만 붙일 수 있다."""
        grouped: dict[int, list[ContactEdge]] = {}
        for edge in self.edges:
            grouped.setdefault(edge.region_id, []).append(edge)
        return {region: tuple(edges) for region, edges in grouped.items()}


def _material_of_region(structure: Structure) -> dict[int, str]:
    return {region.id: region.material for region in structure.regions}


def _elements_by_index(structure: Structure) -> tuple[Element, ...]:
    """이웃 번호는 0-based **요소 인덱스**다(요소 id 가 아니다)."""
    return tuple(structure.elements)


def edge_vertices(element: Element, slot: int) -> tuple[int, int]:
    """이웃 슬롯 `slot` 의 맞은편 변. `mesh.boundary_edges` 와 같은 규칙이다."""
    vertices = element.vertices
    return (vertices[(slot + 1) % 3], vertices[(slot + 2) % 3])


def conductor_clusters(
    structure: Structure, conductors: frozenset[str] | set[str]
) -> tuple[tuple[int, ...], ...]:
    """도체 요소들을 맞닿은 것끼리 묶는다.

    반환값은 요소 **인덱스** 묶음이다. 한 덩어리가 곧 하나의 등전위체다 —
    영역 번호로 나누지 않는 이유는, 같은 금속이 여러 영역으로 쪼개져 있을 수도
    있고 반대로 한 영역이 물리적으로 떨어진 조각들일 수도 있기 때문이다.
    """
    materials = _material_of_region(structure)
    elements = _elements_by_index(structure)
    is_conductor = [
        materials.get(element.region_id) in conductors for element in elements
    ]

    seen = [False] * len(elements)
    clusters: list[tuple[int, ...]] = []
    for start in range(len(elements)):
        if seen[start] or not is_conductor[start]:
            continue
        group: list[int] = []
        queue = deque([start])
        seen[start] = True
        while queue:
            index = queue.popleft()
            group.append(index)
            for neighbor in elements[index].neighbors:
                if neighbor < 0 or seen[neighbor] or not is_conductor[neighbor]:
                    continue
                seen[neighbor] = True
                queue.append(neighbor)
        clusters.append(tuple(sorted(group)))
    return tuple(clusters)


def extent_of(structure: Structure, edges: tuple[ContactEdge, ...]) -> Extent:
    xs: list[float] = []
    ys: list[float] = []
    for edge in edges:
        for vertex in edge.vertices:
            point = structure.coordinates[vertex]
            xs.append(point.x)
            ys.append(point.y)
    return Extent(min(xs), max(xs), min(ys), max(ys))


def _contact_edges_of_cluster(
    structure: Structure,
    cluster: tuple[int, ...],
    conductors: frozenset[str],
) -> tuple[ContactEdge, ...]:
    """덩어리 바깥으로 닿은 변 중 해석 대상 영역 쪽 것만 모은다."""
    materials = _material_of_region(structure)
    elements = _elements_by_index(structure)
    inside = set(cluster)

    semiconductor: list[tuple[bool, ContactEdge]] = []
    insulator: list[tuple[bool, ContactEdge]] = []
    for index in cluster:
        element = elements[index]
        # 이 덩어리 안에서 **원래는 반도체**인 조각(도체로 취급된 poly)인가.
        from_gate_material = materials.get(element.region_id) in SEMICONDUCTORS
        for slot, neighbor in enumerate(element.neighbors):
            if neighbor < 0 or neighbor in inside:
                continue
            other = elements[neighbor]
            material = materials.get(other.region_id)
            if material in conductors:
                continue
            a, b = edge_vertices(element, slot)
            # 변은 받는 쪽 요소에 단다. 방향은 받는 쪽 기준으로 뒤집힌다.
            edge = ContactEdge(
                element_id=other.id, region_id=other.region_id, vertices=(b, a)
            )
            if material in SEMICONDUCTORS:
                semiconductor.append((from_gate_material, edge))
            elif material in INSULATORS:
                insulator.append((from_gate_material, edge))

    # 반도체에 닿았으면 절연체 쪽 변은 버린다.
    #
    # 금속 플러그의 옆면은 층간 절연막에 닿아 있다. 그것도 물리적으로는 금속과
    # 같은 전위지만, 전류가 드나드는 자리가 아니고 전계 판(field plate) 효과는
    # 채널에서 멀어 I-V 에 사실상 영향이 없다. 반면 접촉으로 잡으면 전극 범위가
    # 플러그 몸통 전체로 늘어나 화면에서 실제 접촉면을 가리키지 못한다.
    chosen = semiconductor or insulator
    if not chosen:
        return ()

    # 덩어리에 poly 가 섞여 있으면(도체 모드의 게이트 스택) **poly 가 맞닿은
    # 면만** 남긴다.
    #
    # 금속 플러그와 poly 는 한 덩어리지만, 플러그 옆면은 두꺼운 층간 절연막에
    # 닿아 있다. 그것까지 접촉으로 잡으면 게이트 전위가 ILD 전체에 걸린다 —
    # 실측에서 그 구조는 드리프트-확산 초기해부터 수렴하지 않았다. 게이트로서
    # 의미 있는 면은 게이트 산화막과 측벽 스페이서, 즉 poly 쪽 면이다.
    from_gate = [edge for is_gate, edge in chosen if is_gate]
    if from_gate:
        return tuple(from_gate)
    return tuple(edge for _is_gate, edge in chosen)


def _name_electrodes(
    candidates: list[tuple[Extent, ContactKind, tuple[str, ...], tuple[ContactEdge, ...]]],
) -> tuple[Electrode, ...]:
    """이름을 제안한다. 사용자가 화면에서 고칠 수 있으므로 어림짐작으로 충분하다.

    게이트는 위치가 아니라 **무엇에 닿았는지**로 고른다. poly 에 닿았거나
    (반도체 모드) 산화막에 닿았으면(도체 모드) 게이트다. 나머지는 왼쪽부터
    source, drain 순으로 붙인다.
    """
    ordered = sorted(candidates, key=lambda item: (item[0].x_min + item[0].x_max) / 2)

    def looks_like_gate(kind: ContactKind, materials: tuple[str, ...]) -> bool:
        return kind is ContactKind.INSULATOR or "poly" in materials

    plain_names = deque(["source", "drain"])

    electrodes: list[Electrode] = []
    extra = 0
    for extent, kind, materials, edges in ordered:
        if looks_like_gate(kind, materials):
            name = "gate"
        elif plain_names:
            name = plain_names.popleft()
        else:
            extra += 1
            name = f"contact{extra}"
        electrodes.append(
            Electrode(
                name=name,
                kind=kind,
                materials=materials,
                edges=edges,
                extent=extent,
                origin="metal",
            )
        )
    return tuple(electrodes)


def detect_electrodes(
    structure: Structure,
    *,
    gate_model: GateModel = GateModel.SEMICONDUCTOR,
) -> tuple[Electrode, ...]:
    """금속에서 계면을 찾는다.

    덩어리 하나가 전극 하나다. 한 덩어리가 여러 영역에 닿아도 전극은 하나이고,
    그래서 등전위가 **구성상** 보장된다 — 사용자가 따로 묶어 줄 필요가 없다.
    """
    conductors = gate_model.conductors()
    materials = _material_of_region(structure)

    candidates: list[
        tuple[Extent, ContactKind, tuple[str, ...], tuple[ContactEdge, ...]]
    ] = []
    for cluster in conductor_clusters(structure, conductors):
        edges = _contact_edges_of_cluster(structure, cluster, conductors)
        if not edges:
            # 어디에도 안 닿은 금속 조각. 전기적으로 뜬 것이라 전극이 아니다.
            continue
        touched = tuple(sorted({materials[edge.region_id] for edge in edges}))
        kind = (
            ContactKind.SEMICONDUCTOR
            if any(material in SEMICONDUCTORS for material in touched)
            else ContactKind.INSULATOR
        )
        candidates.append((extent_of(structure, edges), kind, touched, edges))

    return _name_electrodes(candidates)


def backside_candidate(structure: Structure) -> Electrode | None:
    """뒷면 경계를 기판 전극 후보로 내놓는다.

    공정 코드에는 기판 접촉이 없는 것이 보통이다(`nmos.in` 도 없다). 그런데
    기판이 뜨면 소자가 안 풀린다. 그래서 뒷면을 자동으로 제안하되, 확정하지는
    않는다 — SOI 처럼 뒷면이 기판이 아닌 구조도 있다.
    """
    materials = _material_of_region(structure)
    elements = _elements_by_index(structure)

    edges: list[ContactEdge] = []
    for element in elements:
        if materials.get(element.region_id) not in SEMICONDUCTORS:
            continue
        for slot, neighbor in enumerate(element.neighbors):
            if neighbor >= 0:
                continue
            if BoundaryCondition.resolve(neighbor) is not BoundaryCondition.BACKSIDE:
                continue
            edges.append(
                ContactEdge(
                    element_id=element.id,
                    region_id=element.region_id,
                    vertices=edge_vertices(element, slot),
                )
            )
    if not edges:
        return None

    touched = tuple(sorted({materials[edge.region_id] for edge in edges}))
    return Electrode(
        name="body",
        kind=ContactKind.SEMICONDUCTOR,
        materials=touched,
        edges=tuple(edges),
        extent=extent_of(structure, tuple(edges)),
        origin="backside",
    )


def detect_interfaces(
    structure: Structure,
    *,
    gate_model: GateModel = GateModel.SEMICONDUCTOR,
) -> tuple[Electrode, ...]:
    """해석에 쓸 수 있는 계면 전부 — 금속 접촉과 뒷면.

    사용자가 고를 수 있는 것은 이 목록이 전부다. 임의의 경계를 전극이라고
    지정하게 두지 않는다 — 반도체 표면 아무 데나 접촉을 걸면 소자가 아니라
    수치 실험이 되고, 그 결과를 곡선이라고 읽게 된다.
    """
    found = list(detect_electrodes(structure, gate_model=gate_model))
    backside = backside_candidate(structure)
    if backside is not None:
        found.append(backside)
    return tuple(found)
