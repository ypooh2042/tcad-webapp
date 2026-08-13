"""`.str` 구조 파일의 도메인 모델.

전부 불변(frozen)이다. 파싱 결과는 여러 곳(플롯 API, DevSim 변환기)에서 공유되므로
어느 한쪽이 값을 바꾸면 추적 불가능한 버그가 된다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.str_parser.species import SpeciesTable


@dataclass(frozen=True, slots=True)
class Coordinate:
    """`c` 라인. id 는 파일에 적힌 그대로 1-based.

    1D 에서는 x 가 곧 깊이이고 y 는 항상 0 이다. 표면 위에 증착된 층은 x 가
    음수로 나온다(예: oxide 0.075um 증착 → x=-0.075).
    """

    id: int
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Region:
    """`r` 라인. region 하나가 물질 하나에 대응한다."""

    id: int
    material_id: int
    material: str


@dataclass(frozen=True, slots=True)
class Element:
    """`t` 라인. 메시 요소 하나.

    레이아웃은 `D` 라인이 정한다: `t <id> <region_id> <정점 nvrt개>
    <이웃 nedg개> <미확정 2개>`. suprem 바이너리의 ig2_write/ig2_read 를
    역어셈블해 확정했다.
    """

    id: int
    region_id: int
    #: 0-based 좌표 인덱스. 파일에는 1-based 로 적혀 있다.
    vertices: tuple[int, ...]
    #: 0 이상이면 0-based 요소 인덱스, 음수면 경계 조건 코드(boundary.py 참조).
    #: neighbors[i] 는 정점 i 의 맞은편 변을 공유하는 요소다.
    neighbors: tuple[int, ...]
    #: 의미 미확정. 모든 예제에서 (-1, -1) 이며 해석하지 않고 그대로 보존한다.
    extra: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class NodeSolution:
    """`n` 라인. 한 좌표점의 한 물질 쪽 물성값.

    첫 필드는 노드 일련번호가 아니라 **0-based 좌표(point) 인덱스**다
    (바이너리의 mk_nd 첫 인자가 그대로 pt 필드에 들어간다). 계면 점은 인접한
    물질 수만큼 여러 줄로 나타나므로 coordinate_index 는 유일하지 않고,
    `(coordinate_index, material_id)` 조합이 유일하다.

    같은 점이라도 물질에 따라 값이 다르다. 예를 들어 CMOS 예제의 (2.0, 0.0419)
    지점에서 chem_boron 은 oxide 쪽 1.03e17, silicon 쪽 2.07e16 이다. 컨투어를
    그릴 때 반드시 해당 요소의 물질로 조회해야 계면에서 값이 튀지 않는다.
    """

    coordinate_index: int
    material_id: int
    material: str
    values: tuple[float, ...]
    table: SpeciesTable

    def value(self, name: str) -> float:
        """quantity 를 이름으로 조회한다. 위치 상수는 절대 쓰지 않는다."""
        return self.values[self.table.position_of(name)]

    def net_doping(self) -> float:
        """활성 도너 − 활성 억셉터.

        **파일에는 net doping 컬럼이 없다.** 한동안 코드 24 를 그것으로 읽었지만
        상류 impurity.h 는 `GRN`(폴리실리콘 결정립 크기)로 정의한다. 값이 늘
        0 이라 도핑으로 쓰면 도핑이 없는 소자처럼 보였다.
        """
        donors = sum(self.values[i] for i in self.table.donor_positions)
        acceptors = sum(self.values[i] for i in self.table.acceptor_positions)
        return donors - acceptors


@dataclass(frozen=True, slots=True)
class Structure:
    """`.str` 파일 하나의 파싱 결과.

    coordinates 는 0-based 리스트다. Element.vertices 와 NodeSolution.
    coordinate_index 가 모두 이 인덱스를 가리킨다.
    """

    version: str
    dimension: int
    #: 요소당 정점 수. `D` 라인 2번째 필드 (1D=2, 2D=3).
    vertices_per_element: int
    #: 요소당 이웃 수. `D` 라인 3번째 필드 (1D=2, 2D=3).
    neighbors_per_element: int
    coordinates: tuple[Coordinate, ...]
    regions: tuple[Region, ...]
    elements: tuple[Element, ...]
    solutions: tuple[NodeSolution, ...]
    table: SpeciesTable
    temperature_k: float | None
    warnings: tuple[str, ...]
    _solution_index: Mapping[tuple[int, int], NodeSolution]

    @property
    def species(self):
        return self.table.species

    def solution_at(self, coordinate_index: int, material_id: int) -> NodeSolution:
        """좌표점 + 물질로 물성값을 조회한다.

        물질을 반드시 지정해야 한다. 계면 점은 물질마다 값이 다르므로 물질 없이
        조회하면 어느 쪽 값인지 알 수 없다.

        Raises:
            KeyError: 해당 조합이 없을 때. 다른 물질 값으로 대체하지 않는다.
        """
        return self._solution_index[(coordinate_index, material_id)]
