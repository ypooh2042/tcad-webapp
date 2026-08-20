"""도핑 기울기로 목표 격자 크기를 정한다.

기하만 보고 크기를 정하면 도핑이 가파른 자리에서 값이 뭉개진다 — 실측으로
비소 총선량이 13.6% 어긋났다. 접합 깊이가 달라지는 크기다.

기준은 **한 요소를 건너며 농도가 몇 자릿수 바뀌는가**다. 그것을 일정하게
유지하도록 크기를 정하면, 가파른 곳은 촘촘해지고 완만한 곳은 성겨진다.
현대 도구의 해 적응 격자와 같은 생각이다.
"""

from __future__ import annotations

from math import hypot, log10

from app.str_parser.models import Structure

#: 한 요소를 건너며 허용할 농도 변화(자릿수).
#:
#: 0.3 이면 요소 하나에서 농도가 두 배쯤 바뀐다. 더 조이면 점이 급격히 늘고,
#: 풀면 가파른 접합이 뭉개진다.
_SPAN_PER_ELEMENT = 0.3


def node_sizes(structure: Structure, floor: float, ceiling: float) -> tuple[float, ...]:
    """점마다의 목표 크기.

    Args:
        floor: 이보다 작게는 요구하지 않는다.
        ceiling: 이보다 크게는 허용하지 않는다.
    """
    coords = structure.coordinates
    material = {r.id: r.material_id for r in structure.regions}
    names = [s.name for s in structure.species if s.name.startswith("chem_")]

    sizes = [ceiling] * len(coords)
    if not names:
        return tuple(sizes)

    for element in structure.elements:
        m = material.get(element.region_id)
        if m is None:
            continue

        peak = []
        for i in element.vertices:
            try:
                row = structure.solution_at(i, m)
            except KeyError:
                peak = []
                break
            value = max(row.value(n) for n in names)
            peak.append(log10(value) if value > 0 else None)
        if len(peak) != 3 or any(v is None for v in peak):
            continue

        span = max(peak) - min(peak)
        if span <= 0:
            continue

        # 이 요소에서 가장 긴 변. 그 길이에서 span 만큼 바뀌었으니, 허용치에
        # 맞추려면 길이를 그 비율로 줄여야 한다.
        p = [coords[i] for i in element.vertices]
        longest = max(
            hypot(p[i].x - p[(i + 1) % 3].x, p[i].y - p[(i + 1) % 3].y)
            for i in range(3)
        )
        if longest <= 0:
            continue

        target = longest * _SPAN_PER_ELEMENT / span
        target = min(max(target, floor), ceiling)
        for i in element.vertices:
            if target < sizes[i]:
                sizes[i] = target

    return tuple(min(max(v, floor), ceiling) for v in sizes)
