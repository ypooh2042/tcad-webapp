"""스펙이 이름으로 가리킨 전극을 구조에서 다시 뽑는다.

브라우저가 보낸 좌표를 그대로 믿지 않는 이유: 스펙은 저장되고 재사용되는데,
그 사이에 다른 구조에 붙으면 기하가 안 맞는다. 이름과 상자만 받아서 **구조에서
다시 계산**하면, 안 맞을 때 조용히 엉뚱한 자리를 잡는 대신 오류가 난다.
"""

from __future__ import annotations

from dataclasses import replace

from app.devsim.electrodes import (
    INSULATORS,
    SEMICONDUCTORS,
    ContactEdge,
    ContactKind,
    Electrode,
    edge_vertices,
    extent_of,
    backside_candidate,
    detect_electrodes,
)
from app.devsim.spec import Box, DeviceSpec
from app.str_parser.models import Structure


class ElectrodeNotFound(ValueError):
    """스펙이 가리킨 전극을 구조에서 찾지 못했다."""


def _picked(structure: Structure, label: str, box: Box) -> Electrode:
    """상자 안에 완전히 들어간 바깥 경계 변을 전극으로 삼는다.

    변의 **양 끝**이 다 들어와야 한다. 한쪽만 걸린 변까지 잡으면 사용자가 그은
    사각형 밖으로 전극이 삐져나간다.
    """
    materials = {region.id: region.material for region in structure.regions}
    inside = lambda x, y: (  # noqa: E731
        box.x_min <= x <= box.x_max and box.y_min <= y <= box.y_max
    )

    edges: list[ContactEdge] = []
    for element in structure.elements:
        material = materials.get(element.region_id)
        if material not in (SEMICONDUCTORS | INSULATORS):
            continue
        for slot, neighbor in enumerate(element.neighbors):
            if neighbor >= 0:
                continue
            vertices = edge_vertices(element, slot)
            points = [structure.coordinates[v] for v in vertices]
            if not all(inside(p.x, p.y) for p in points):
                continue
            edges.append(
                ContactEdge(
                    element_id=element.id,
                    region_id=element.region_id,
                    vertices=vertices,
                )
            )
    if not edges:
        raise ElectrodeNotFound(
            f"{label!r}: 찍은 범위 안에 경계가 없습니다. 구조 바깥선 위를 지정해 주세요."
        )

    touched = tuple(sorted({materials[edge.region_id] for edge in edges}))
    kind = (
        ContactKind.SEMICONDUCTOR
        if any(material in SEMICONDUCTORS for material in touched)
        else ContactKind.INSULATOR
    )
    return Electrode(
        name=label,
        kind=kind,
        materials=touched,
        edges=tuple(edges),
        extent=extent_of(structure, tuple(edges)),
    )


def resolve_electrodes(
    structure: Structure, spec: DeviceSpec
) -> tuple[Electrode, ...]:
    """스펙의 전극 목록을 실제 전극으로 바꾼다. 이름은 사용자 표시명으로 바꾼다."""
    detected = {
        electrode.name: electrode
        for electrode in detect_electrodes(structure, gate_model=spec.gate_model)
    }

    resolved: list[Electrode] = []
    for choice in spec.electrodes:
        if choice.origin == "detected":
            found = detected.get(choice.key or "")
            if found is None:
                raise ElectrodeNotFound(
                    f"{choice.key!r} 전극이 이 구조에 없습니다. "
                    f"있는 것: {', '.join(sorted(detected)) or '없음'}"
                )
            resolved.append(replace(found, name=choice.label))
        elif choice.origin == "backside":
            found = backside_candidate(structure)
            if found is None:
                raise ElectrodeNotFound(
                    f"{choice.label!r}: 이 구조에는 뒷면 경계가 없습니다."
                )
            resolved.append(replace(found, name=choice.label))
        else:
            assert choice.box is not None
            resolved.append(_picked(structure, choice.label, choice.box))
    return tuple(resolved)
