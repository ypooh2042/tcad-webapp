"""노드별 순 도핑을 뽑아 DevSim 으로 보낼 준비를 한다.

`.str` 에는 net doping 컬럼이 없다(코드 24 는 폴리 결정립 크기다 —
`str_parser/models.py:81` 에 그 착오의 기록이 있다). 활성 도너에서 활성 억셉터를
뺀 값을 쓴다.

**점과 노드를 구분해야 한다.** 계면 점은 인접한 물질 수만큼 값을 갖는다. 영역의
재질로 물어야 계면에서 농도가 튀지 않는다 — 플롯 쪽이 같은 이유로 같은 규칙을
쓴다(`plotting/surface.py`).
"""

from __future__ import annotations

from enum import Enum

from app.str_parser.models import Structure
from app.str_parser.species import SpeciesTable


class DopingSource(Enum):
    """어느 컬럼에서 도핑을 읽었는가.

    `ACTIVE` 가 물리적으로 맞다. 다만 확산·활성화를 거치지 않은 구조에는 활성
    컬럼이 아예 없을 수 있고, 그때 활성만 고집하면 도핑이 0 인 소자가 나와
    아무 곡선도 안 나온다. 그래서 화학 농도로 떨어진다.
    """

    ACTIVE = "active"
    CHEMICAL = "chemical"


def doping_source(table: SpeciesTable) -> DopingSource:
    if table.donor_positions or table.acceptor_positions:
        return DopingSource.ACTIVE
    return DopingSource.CHEMICAL


#: 화학 농도로 떨어질 때 쓰는 이름. 활성 컬럼과 짝이 되는 것들이다.
_CHEMICAL_DONORS = ("chem_arsenic", "chem_phosphorus", "chem_antimony")
_CHEMICAL_ACCEPTORS = ("chem_boron",)


def _chemical_positions(table: SpeciesTable) -> tuple[tuple[int, ...], tuple[int, ...]]:
    donors = tuple(
        table.position_of(name) for name in _CHEMICAL_DONORS if table.has(name)
    )
    acceptors = tuple(
        table.position_of(name) for name in _CHEMICAL_ACCEPTORS if table.has(name)
    )
    return donors, acceptors


def net_doping_by_point(structure: Structure, material_id: int) -> dict[int, float]:
    """해당 물질 쪽 값으로 읽은 점별 순 도핑(cm⁻³).

    농도는 `.str` 에 이미 cm⁻³ 로 들어 있어 단위 변환이 없다.
    """
    source = doping_source(structure.table)
    if source is DopingSource.ACTIVE:
        donors = structure.table.donor_positions
        acceptors = structure.table.acceptor_positions
    else:
        donors, acceptors = _chemical_positions(structure.table)

    values: dict[int, float] = {}
    for solution in structure.solutions:
        if solution.material_id != material_id:
            continue
        total = sum(solution.values[i] for i in donors) - sum(
            solution.values[i] for i in acceptors
        )
        values[solution.coordinate_index] = total
    return values
