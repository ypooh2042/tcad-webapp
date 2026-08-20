"""컨테이너로 건너갈 장치 설명(JSON)을 만든다.

컨테이너 안에서 도는 스크립트는 `.str` 을 모른다. SUPREM 을 아는 것은 여기까지고,
넘어가는 것은 좌표·요소·도핑·바이어스 계획뿐이다. 그래서 스크립트가 짧고, 사용자
입력이 코드가 될 여지가 없다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.devsim.doping import doping_source, net_doping_by_point
from app.devsim.electrodes import Electrode
from app.devsim.mesh import UM_TO_CM, DeviceMesh, build_device_mesh
from app.devsim.resolve import resolve_electrodes
from app.devsim.spec import DeviceSpec, total_points
from app.str_parser.models import Structure

#: 좌표를 열쇠로 쓸 때의 자리수. DevSim 이 우리가 준 값을 그대로 돌려주므로
#: 반올림은 부동소수점 표기 차이를 막는 보험이다. cm 단위에서 1e-12 은
#: 1e-8 µm 이라, 가장 짧은 변(1e-3 µm)보다 다섯 자리 작아 충돌하지 않는다.
COORDINATE_DIGITS = 12


def _bias_of_electrode(spec: DeviceSpec) -> dict[str, str]:
    return {
        label: bias.name for bias in spec.biases for label in bias.electrodes
    }


def _doping_points(
    structure: Structure, mesh: DeviceMesh
) -> dict[str, list[tuple[float, float, float]]]:
    """반도체 영역마다 (x, y, NetDoping) 목록.

    DevSim 의 노드 순서를 가정하지 않는다. 스크립트가 `x`/`y` 를 되읽어 이 좌표로
    찾아 쓴다 — 순서를 맞히려 들면 DevSim 이 순서를 바꾸는 날 조용히 틀린다.
    """
    by_material: dict[int, dict[int, float]] = {}
    result: dict[str, list[tuple[float, float, float]]] = {}

    material_of_region = {region.id: region.material_id for region in structure.regions}
    used: dict[int, set[int]] = {}
    for element in structure.elements:
        used.setdefault(element.region_id, set()).update(element.vertices)

    for region in mesh.regions:
        if not region.is_semiconductor:
            continue
        material_id = material_of_region[region.region_id]
        if material_id not in by_material:
            by_material[material_id] = net_doping_by_point(structure, material_id)
        values = by_material[material_id]

        points: list[tuple[float, float, float]] = []
        for vertex in sorted(used.get(region.region_id, ())):
            point = structure.coordinates[vertex]
            points.append(
                (
                    round(point.x * UM_TO_CM, COORDINATE_DIGITS),
                    round(-point.y * UM_TO_CM, COORDINATE_DIGITS),
                    values.get(vertex, 0.0),
                )
            )
        result[region.name] = points
    return result


def build_payload(
    structure: Structure,
    spec: DeviceSpec,
    electrodes: Sequence[Electrode] | None = None,
) -> dict[str, Any]:
    """`device.json` 의 내용."""
    resolved = tuple(electrodes) if electrodes else resolve_electrodes(structure, spec)
    mesh = build_device_mesh(structure, resolved, gate_model=spec.gate_model)
    bias_of = _bias_of_electrode(spec)

    sweep = spec.sweep_bias()
    plan = {
        "sweep": {"bias": sweep.name, "values": sweep.points()},
        "steps": spec.step_combinations(),
        "constants": {bias.name: bias.points()[0] for bias in spec.const_biases()},
        "total": total_points(spec),
    }

    return {
        "temperature_k": spec.temperature_k,
        "gate_model": spec.gate_model.value,
        "doping_source": doping_source(structure.table).value,
        "mesh": {
            "coordinates": list(mesh.coordinates),
            "elements": list(mesh.elements),
            "physical_names": list(mesh.physical_names),
        },
        "regions": [
            {
                "name": region.name,
                "material": region.material,
                "devsim_material": region.devsim_material,
                "is_semiconductor": region.is_semiconductor,
            }
            for region in mesh.regions
        ],
        "interfaces": [
            {"name": i.name, "region0": i.region0, "region1": i.region1}
            for i in mesh.interfaces
        ],
        "contacts": [
            {
                "name": contact.name,
                "electrode": contact.electrode,
                "region": contact.region,
                "kind": contact.kind.value,
                "bias": bias_of[contact.electrode],
            }
            for contact in mesh.contacts
        ],
        "doping": {
            name: [list(point) for point in points]
            for name, points in _doping_points(structure, mesh).items()
        },
        "plan": plan,
        "coordinate_digits": COORDINATE_DIGITS,
    }
