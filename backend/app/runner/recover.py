"""죽은 실행을 마지막 체크포인트에서 다시 잇는다.

**정상 실행은 이 코드를 지나가지도 않는다.** 성공한 실행을 건드리면 결과가
달라지므로 오직 panic 으로 죽었을 때만 개입한다.

왜 이어 붙이기가 통하는가: `.str` 은 좌표·영역·삼각형·물성값을 다 담지만 점마다
목표 격자간격(`pt[]->spac`)은 담지 않는다(`mesh/ig2_meshio.c` 에 없다). 그 값이
공정 내내 쌓여 문제를 만드는데, 파일로 나갔다 들어오면 씻긴다 — 실측으로 6e13
흐름이 통째로는 step 17 에서 죽지만, step 16 결과에서 다시 시작하면 남은 36
단계를 완주했다.

격자가 병적일 때는 다시 잇기 전에 메시를 새로 짠다(`app/remesh`). 늘 다시 짜지
않는 이유는 값 보간이 선량을 조금 움직이기 때문이다 — 필요할 때만 치른다.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import dist
from pathlib import Path

from app.runner.results import STRUCTURE_OUT_RE
from app.str_parser.models import Structure

#: 이보다 짧은 변이 있으면 격자가 퇴화했다고 본다(µm 단위 — `.str` 좌표가 µm 다).
#:
#: 1 nm. refine/etch_elem.c 의 SNAP_DIST 와 같은 값이고, 이번 세션에서 추적한
#: 사망의 앞자리에는 늘 이 크기의 변이 있었다.
DEGENERATE_EDGE = 1.0e-3

#: 죽으면서 남기는 덤프. 이어 갈 수 있는 체크포인트가 아니다.
_PANIC_DUMP = "panic.str"


@dataclass(frozen=True, slots=True)
class Checkpoint:
    #: 다시 시작할 구조 파일.
    structure: Path
    #: 그 뒤에 남은 소스. `structure in=` 으로 시작한다.
    remaining: str


def find_checkpoint(source: str, workdir: Path) -> Checkpoint | None:
    """마지막으로 성공한 `structure out=` 과 그 뒤에 남은 소스.

    이어 갈 것이 없으면(체크포인트가 없거나 이미 끝까지 갔으면) None.
    """
    last: tuple[str, int] | None = None
    for match in STRUCTURE_OUT_RE.finditer(source):
        name = Path(match.group(1)).name
        if name == _PANIC_DUMP:
            continue
        if (workdir / name).exists():
            last = (name, match.end())

    if last is None:
        return None

    name, end = last
    # 그 줄의 끝까지 넘긴다. 줄 도중에서 자르면 남은 소스가 깨진다.
    newline = source.find("\n", end)
    rest = source[newline + 1 :] if newline >= 0 else ""
    if not rest.strip():
        return None

    return Checkpoint(workdir / name, f"structure in={name}\n{rest}")


def needs_remesh(structure: Structure) -> bool:
    """격자를 다시 짜야 할 만큼 퇴화했는가.

    판정은 **sub-nm 변**이다. 최소각으로 재려 했으나 정상 구조도 1~2 도가 나와
    갈라지지 않았다(실측). 반면 sub-nm 변은 식각·증착의 퇴화가 남긴 흔적이라
    정상 구조에는 거의 없다.
    """
    if structure.dimension != 2 or structure.vertices_per_element != 3:
        return False

    coords = structure.coordinates
    seen: set[tuple[int, int]] = set()
    for element in structure.elements:
        v = element.vertices
        for i in range(3):
            a, b = v[i], v[(i + 1) % 3]
            key = (a, b) if a < b else (b, a)
            if key in seen:
                continue
            seen.add(key)
            if dist((coords[a].x, coords[a].y), (coords[b].x, coords[b].y)) < DEGENERATE_EDGE:
                return True
    return False
