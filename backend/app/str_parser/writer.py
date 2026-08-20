"""`.str` 쓰기.

메시를 다시 짜서 시뮬레이터에 돌려주려면 이 형식으로 되쓸 수 있어야 한다.
읽기(`parser.py`)의 정확한 역이다.

**형식은 `mesh/ig2_meshio.c` 의 `ig2_write()` 를 그대로 따른다.** 공백 개수까지
그렇다 — `n %d   %d  ` 처럼 손으로 맞춘 자리가 있고, 좌표는 `%g`(6 자리),
물성값은 `%e` 다. 파이썬의 `%g`/`%e` 가 C 와 같은 문자열을 낸다는 것은 실측으로
확인했다(픽스처 전체에서 불일치 0).

**직접 만들지 않는 레코드는 원본 줄을 그대로 옮긴다**(`v`, `D`, `M`, `s`, `I`).
그것들은 메시와 무관한데 다시 만들면 틀릴 여지만 생긴다. 그래서 이 함수는
원본 텍스트를 함께 받는다.
"""

from __future__ import annotations

from app.str_parser.models import Structure

#: ig2_write 가 쓰는 레코드 순서.
_ORDER = ("v", "D", "c", "r", "t", "M", "s", "n", "I")

#: 우리가 메시에서 다시 만드는 레코드. 나머지는 원본에서 옮긴다.
_OWNED = frozenset({"c", "r", "t", "n"})


def _kept_lines(source: str) -> dict[str, list[str]]:
    """원본에서 그대로 옮길 줄을 종류별로 모은다."""
    kept: dict[str, list[str]] = {}
    for line in source.splitlines():
        tag = line.split(" ", 1)[0] if line else ""
        if tag and tag not in _OWNED:
            kept.setdefault(tag, []).append(line)
    return kept


def write_structure(structure: Structure, source: str) -> str:
    """구조를 `.str` 텍스트로 만든다.

    Args:
        structure: 쓸 내용. 메시를 갈아끼웠다면 그 새 메시가 여기 들어 있다.
        source: 원본 파일 텍스트. 우리가 만들지 않는 레코드를 여기서 옮긴다.

    Returns:
        `.str` 텍스트. 끝에 개행이 붙는다.
    """
    kept = _kept_lines(source)
    out: list[str] = []

    for tag in _ORDER:
        if tag in _OWNED:
            out.extend(_own(tag, structure))
        else:
            out.extend(kept.get(tag, []))

    return "".join(line + "\n" for line in out)


def _own(tag: str, s: Structure) -> list[str]:
    if tag == "c":
        return [_coordinate(c, s.dimension) for c in s.coordinates]
    if tag == "r":
        return [f"r {r.id}   {r.material_id}" for r in s.regions]
    if tag == "t":
        return [_element(e) for e in s.elements]
    if tag == "n":
        return [_node(n) for n in s.solutions]
    raise AssertionError(tag)


def _coordinate(c, dimension: int) -> str:
    """`c %d` + 차원 수만큼 ` %g` + `  0`.

    1 차원에서는 x 만 쓴다. 파서가 y 를 0 으로 채워 두므로 dimension 을 봐야
    한다 — 그러지 않으면 1D 파일에 없던 열이 생긴다.
    """
    values = (c.x, c.y)[:dimension]
    return f"c {c.id}" + "".join(f" {v:g}" for v in values) + "  0"


def _element(e) -> str:
    """`t <id> <region> <정점...> <이웃...> <extra...> ` — 끝에 공백이 붙는다.

    파일은 1-based 정점 인덱스를, 이웃은 있으면 1-based 요소 번호를 쓴다
    (`tcode` 매크로). 음수는 경계 조건 코드이므로 손대지 않는다.
    """
    fields = [str(e.id), str(e.region_id)]
    fields += [str(v + 1) for v in e.vertices]
    fields += [str(n + 1 if n >= 0 else n) for n in e.neighbors]
    fields += [str(x) for x in e.extra]
    return "t " + " ".join(fields) + " "


def _node(n) -> str:
    """`n <0-based 점> <물질>  <값들 %e>`.

    첫 필드는 노드 번호가 아니라 **0-based 점 인덱스**다. 계면 점은 인접 물질
    수만큼 여러 줄로 나온다.
    """
    head = f"n {n.coordinate_index}   {n.material_id}  "
    return head + "".join(f" {v:e}" for v in n.values)
