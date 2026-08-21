"""스펙이 이름으로 가리킨 계면을 구조에서 다시 뽑아 전극으로 묶는다.

브라우저가 보낸 좌표를 그대로 믿지 않는 이유: 스펙은 저장되고 재사용되는데,
그 사이에 다른 구조에 붙으면 기하가 안 맞는다. 이름만 받아서 **구조에서 다시
계산**하면, 안 맞을 때 조용히 엉뚱한 자리를 잡는 대신 오류가 난다.
"""

from __future__ import annotations

from app.devsim.electrodes import (
    SEMICONDUCTORS,
    ContactEdge,
    ContactKind,
    Electrode,
    detect_interfaces,
    extent_of,
)
from app.devsim.spec import DeviceSpec
from app.str_parser.models import Structure


class ElectrodeNotFound(ValueError):
    """스펙이 가리킨 계면을 구조에서 찾지 못했다."""


def resolve_electrodes(
    structure: Structure, spec: DeviceSpec
) -> tuple[Electrode, ...]:
    """전극마다 그에 묶인 계면들의 변을 합친다.

    합친 전극이 곧 DevSim 접촉 하나(정확히는 영역마다 하나)이고, 전압원이
    거기에 1:1 로 붙는다.
    """
    detected = detect_interfaces(structure, gate_model=spec.gate_model)
    available = {found.name: found for found in detected}
    if len(available) != len(detected):
        # 이름이 곧 열쇠다. 겹치면 뒤엣것이 앞엣것을 덮어써서 한쪽 계면이
        # **엉뚱한 자리에 걸린 채로** 해석이 돌아간다 — 오류 없이 틀린 곡선이
        # 나오는 것보다 여기서 멈추는 편이 낫다.
        raise ElectrodeNotFound(
            "계면 이름이 겹칩니다: "
            f"{sorted(one.name for one in detected)}. 구조 인식에 문제가 있습니다."
        )

    resolved: list[Electrode] = []
    for choice in spec.electrodes:
        edges: list[ContactEdge] = []
        materials: set[str] = set()
        origins: set[str] = set()
        for key in choice.interfaces:
            found = available.get(key)
            if found is None:
                raise ElectrodeNotFound(
                    f"{key!r} 계면이 이 구조에 없습니다. "
                    f"있는 것: {', '.join(sorted(available)) or '없음'}"
                )
            edges.extend(found.edges)
            materials.update(found.materials)
            origins.add(found.origin)

        if not edges:
            raise ElectrodeNotFound(
                f"{choice.label!r} 전극에 붙은 계면에 접촉 변이 없습니다."
            )

        # 반도체에 닿은 변이 하나라도 있으면 반도체 접촉으로 푼다. 절연막에만
        # 닿은 접촉은 전위만 걸리고 전류가 흐르지 않는다.
        kind = (
            ContactKind.SEMICONDUCTOR
            if any(material in SEMICONDUCTORS for material in materials)
            else ContactKind.INSULATOR
        )
        resolved.append(
            Electrode(
                name=choice.label,
                kind=kind,
                materials=tuple(sorted(materials)),
                edges=tuple(edges),
                extent=extent_of(structure, tuple(edges)),
                origin="metal" if origins == {"metal"} else "mixed",
            )
        )
    return tuple(resolved)
