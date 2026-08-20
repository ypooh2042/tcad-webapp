"""새 메시가 고정해야 할 것을 뽑아낸다.

형상을 유지하려면 두 가지를 제약으로 걸어야 한다.

    바깥 경계 — 건너편에 요소가 없는 변. 경계 조건 코드가 여기에만 있다
                (`t` 라인의 음수 이웃 필드. `'b'` 레코드는 리더가 무시한다).
    물질 계면 — 건너편 요소의 영역이 다른 변.

안쪽 변은 고정하지 않는다. 그래야 다시 짤 여지가 남는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.str_parser.models import Structure

_VERTICES = 3


def _require_2d(structure: Structure) -> None:
    if structure.dimension != 2 or structure.vertices_per_element != _VERTICES:
        raise ValueError(
            "메시 재구성은 2 차원 구조만 다룹니다 "
            f"(차원 {structure.dimension}, 요소당 정점 {structure.vertices_per_element})"
        )


@dataclass(frozen=True, slots=True)
class Segment:
    """새 메시가 그대로 가져가야 할 변."""

    #: 0-based 좌표 인덱스.
    a: int
    b: int
    #: 이 변의 양쪽 영역 id. 바깥이면 right_region 이 None 이다.
    left_region: int
    right_region: int | None
    #: 바깥일 때의 경계 조건 코드(음수). 계면이면 0.
    bc: int

    @property
    def is_outer(self) -> bool:
        return self.right_region is None


def constrained_segments(structure: Structure) -> tuple[Segment, ...]:
    """고정할 변을 중복 없이 모은다.

    계면은 양쪽 요소가 각각 들고 있으므로 한 번만 담는다. 중복으로 주면 gmsh
    가 겹친 선을 받아 메시가 깨진다.

    Raises:
        ValueError: 2 차원이 아닐 때. 1 차원은 요소가 2 절점이라 변 개념이
            다르고, 애초에 다시 짤 이유도 없다. 조용히 잘못 읽으면 엉뚱한
            기하가 나온다.
    """
    _require_2d(structure)
    by_index = {e.id: e for e in structure.elements}
    seen: dict[tuple[int, int], Segment] = {}

    for element in structure.elements:
        v = element.vertices
        for i in range(_VERTICES):
            # neighbors[i] 는 **정점 i 의 맞은편 변**을 공유하는 요소다.
            a, b = v[(i + 1) % _VERTICES], v[(i + 2) % _VERTICES]
            key = (min(a, b), max(a, b))
            if key in seen:
                continue

            code = element.neighbors[i]
            if code < 0:
                seen[key] = Segment(a, b, element.region_id, None, code)
                continue

            other = _element_at(structure, by_index, code)
            if other is None or other.region_id == element.region_id:
                continue
            seen[key] = Segment(a, b, element.region_id, other.region_id, 0)

    return tuple(seen.values())


def _element_at(structure: Structure, by_index: dict[int, object], code: int):
    """이웃 코드가 가리키는 요소.

    파서가 파일의 1-based 값을 0-based 로 낮춰 두었으므로 위치로 찾는다.
    다만 요소가 순서대로 있다고 가정하지 않는다 — id 로도 확인한다.
    """
    if 0 <= code < len(structure.elements):
        candidate = structure.elements[code]
        if candidate.id == code + 1:
            return candidate
    return by_index.get(code + 1)


def region_loops(structure: Structure) -> dict[int, list[list[int]]]:
    """영역마다 닫힌 경계 루프들.

    한 영역이 여러 루프를 가질 수 있다 — 구멍이 있거나(예: 폴리를 감싼 산화막)
    조각이 떨어져 있을 때다. 각 루프는 첫 점으로 되돌아온다.

    Raises:
        ValueError: 경계를 닫지 못했을 때. 조용히 넘기면 형상이 달라진 채
            메시가 만들어진다.
    """
    incident: dict[int, dict[int, list[int]]] = {}
    for segment in constrained_segments(structure):
        for region in (segment.left_region, segment.right_region):
            if region is None:
                continue
            side = incident.setdefault(region, {})
            side.setdefault(segment.a, []).append(segment.b)
            side.setdefault(segment.b, []).append(segment.a)

    return {region: _loops(region, side) for region, side in incident.items()}


def _loops(region: int, side: dict[int, list[int]]) -> list[list[int]]:
    """인접 관계를 따라가며 닫힌 고리로 만든다."""
    remaining = {point: list(neighbours) for point, neighbours in side.items()}
    loops: list[list[int]] = []

    while remaining:
        start = next(iter(remaining))
        loop = [start]
        current = start

        while True:
            options = remaining.get(current)
            if not options:
                raise ValueError(
                    f"영역 {region} 의 경계가 점 {current} 에서 끊겼습니다"
                )
            nxt = options.pop()
            remaining[current] = options
            if not options:
                del remaining[current]

            back = remaining.get(nxt)
            if back is not None and current in back:
                back.remove(current)
                if not back:
                    del remaining[nxt]

            loop.append(nxt)
            current = nxt
            if nxt == start:
                break

        loops.append(loop)

    return loops
