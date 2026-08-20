"""gmsh 출력(`.msh` 2.2 ASCII) 읽기.

2.2 만 읽는다. 4.x 는 구조가 달라서 같은 코드로 다룰 수 없고, 조용히 잘못
읽느니 멈추는 편이 낫다. 호출부가 `-format msh2` 로 고정해 부른다.
"""

from __future__ import annotations

from dataclasses import dataclass

#: `$Elements` 의 요소 종류. 2 절점 선(1)은 경계 곡선에서 나온 것이라 버린다.
_TRIANGLE = 2


@dataclass(frozen=True, slots=True)
class MeshTriangle:
    #: 0-based 점 인덱스.
    vertices: tuple[int, int, int]
    #: Physical Surface 번호 = 우리가 넣은 영역 id.
    region_id: int


@dataclass(frozen=True, slots=True)
class Mesh:
    points: tuple[tuple[float, float], ...]
    triangles: tuple[MeshTriangle, ...]


def read_msh(text: str) -> Mesh:
    lines = text.splitlines()

    version = _section(lines, "MeshFormat")[0].split()[0]
    if not version.startswith("2.2"):
        raise ValueError(f"`.msh` 2.2 만 읽습니다 (받은 것: {version})")

    raw_nodes = _section(lines, "Nodes")
    count = int(raw_nodes[0])
    # 번호가 1..N 이 아닐 수 있으므로 대응표를 만든다.
    order: dict[int, int] = {}
    points: list[tuple[float, float]] = []
    for row in raw_nodes[1 : 1 + count]:
        f = row.split()
        order[int(f[0])] = len(points)
        points.append((float(f[1]), float(f[2])))

    raw_elements = _section(lines, "Elements")
    triangles: list[MeshTriangle] = []
    for row in raw_elements[1 : 1 + int(raw_elements[0])]:
        f = [int(v) for v in row.split()]
        if f[1] != _TRIANGLE:
            continue
        ntags = f[2]
        tags = f[3 : 3 + ntags]
        nodes = f[3 + ntags : 6 + ntags]
        triangles.append(
            MeshTriangle(tuple(order[n] for n in nodes), tags[0] if tags else 0)
        )

    if not triangles:
        raise ValueError("삼각형이 하나도 없습니다")

    return Mesh(tuple(points), tuple(triangles))


def _section(lines: list[str], name: str) -> list[str]:
    try:
        start = lines.index(f"${name}")
        end = lines.index(f"$End{name}")
    except ValueError as exc:
        raise ValueError(f"`.msh` 에 ${name} 구역이 없습니다") from exc
    return lines[start + 1 : end]
