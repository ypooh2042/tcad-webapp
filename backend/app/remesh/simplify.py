"""경계에서 의미 없이 촘촘한 점을 걷어낸다.

경계를 글자 그대로 보존하면 식각이 남긴 sub-nm 선분이 그대로 남고, 새 메시가
그 자리에서 품질을 잃는다(실측: 경계를 보존한 재메시의 최소각이 3~13° 에
머물렀다). 그 점들은 형상을 담고 있지 않다 — 격자 연산의 부산물이다.

**지우지 않는 것**

    갈래점 — 제약 변이 셋 이상 만나는 점. 영역 셋이 만나는 자리다.
    모서리 — 물질 조합이나 경계 조건이 바뀌는 점.

**지우는 기준**은 형상 오차다. 그 점을 빼고 이웃끼리 이었을 때 경계가 움직이는
거리가 허용오차 이하일 때만 뺀다. 그래서 오차가 허용오차로 묶인다.
"""

from __future__ import annotations

from math import hypot

from app.remesh.geometry import constrained_segments
from app.str_parser.models import Structure


def simplify_boundary(structure: Structure, tolerance: float) -> set[int]:
    """남길 경계 점의 집합.

    Args:
        tolerance: 경계가 움직여도 되는 최대 거리(cm). 0 이면 아무것도 지우지
            않는다.
    """
    segments = constrained_segments(structure)
    neighbours: dict[int, list[int]] = {}
    kinds: dict[int, set] = {}
    for s in segments:
        neighbours.setdefault(s.a, []).append(s.b)
        neighbours.setdefault(s.b, []).append(s.a)
        signature = (s.left_region, s.right_region, s.bc)
        kinds.setdefault(s.a, set()).add(signature)
        kinds.setdefault(s.b, set()).add(signature)

    every = set(neighbours)
    if tolerance <= 0:
        return every

    # 지울 수 없는 점부터 확정한다.
    keep = {i for i in every if len(neighbours[i]) != 2 or len(kinds[i]) > 1}

    coords = structure.coordinates
    for chain in _chains(neighbours, keep, every):
        keep |= _douglas_peucker(chain, coords, tolerance)

    return keep


def _chains(neighbours, fixed, every) -> list[list[int]]:
    """고정점 사이의 점 줄기들. 각 줄기는 양끝이 고정점이다.

    고정점이 하나도 없는 닫힌 고리(예: 사방이 같은 물질인 섬)는 그 고리의 한
    점을 임의로 고정해 끊는다 — 그러지 않으면 시작점을 정할 수 없다.
    """
    chains: list[list[int]] = []
    seen: set[tuple[int, int]] = set()

    starts = sorted(fixed) if fixed else sorted(every)[:1]
    if not fixed and starts:
        fixed = {starts[0]}

    for start in starts:
        for first in neighbours.get(start, []):
            if (start, first) in seen:
                continue
            chain = [start]
            previous, current = start, first
            while True:
                seen.add((previous, current))
                seen.add((current, previous))
                chain.append(current)
                if current in fixed:
                    break
                nxt = [n for n in neighbours[current] if n != previous]
                if len(nxt) != 1:
                    break
                previous, current = current, nxt[0]
            if len(chain) > 2:
                chains.append(chain)
    return chains


def _douglas_peucker(chain, coords, tolerance) -> set[int]:
    """줄기에서 남길 점. 지워지는 점은 **남는 선**에서 허용오차 이내다.

    한 점씩 그리디로 지우면 지울수록 현이 원래 선에서 멀어져 오차가 쌓인다
    (실측: 허용오차 5e-4 인데 0.796 만큼 어긋났다). 분할 정복으로 하면 각
    단계에서 구간 전체의 최대 이탈을 보므로 오차가 구조적으로 묶인다.
    """
    keep = {chain[0], chain[-1]}
    stack = [(0, len(chain) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        a, b = coords[chain[lo]], coords[chain[hi]]
        worst, at = -1.0, -1
        for k in range(lo + 1, hi):
            d = _offset(coords[chain[k]], a, b)
            if d > worst:
                worst, at = d, k
        if worst > tolerance:
            keep.add(chain[at])
            stack.append((lo, at))
            stack.append((at, hi))
    return keep


def _offset(point, a, b) -> float:
    """점을 빼고 a-b 를 이었을 때 경계가 움직이는 거리."""
    dx, dy = b.x - a.x, b.y - a.y
    length = dx * dx + dy * dy
    if length == 0:
        return hypot(point.x - a.x, point.y - a.y)
    t = ((point.x - a.x) * dx + (point.y - a.y) * dy) / length
    t = max(0.0, min(1.0, t))
    return hypot(point.x - (a.x + t * dx), point.y - (a.y + t * dy))
