"""`.str` 파일의 species 코드 사전.

`s` 라인은 quantity 코드를 나열하고, 그 나열 순서가 `n` 라인 값의 순서를 정한다.
컬럼 위치는 파일마다 달라지므로(같은 도펀트라도 배치가 바뀐다) 위치 상수를 쓰면
반드시 깨진다. 코드 → 이름 조회만이 안전한 접근이다.

사전 근거는 SUPREM4GS/STR_FILE_FORMAT.md 참조. 실측 파일 3종을 교차 대조해 확정했다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class DopantRole(Enum):
    """Net doping 계산에 쓰이는 전기적 역할.

    data/modelrc 에 `antimony donor`, `boron acceptor` 등으로 정의돼 있다.
    """

    DONOR = "donor"
    ACCEPTOR = "acceptor"


@dataclass(frozen=True, slots=True)
class Species:
    """`.str` 값 한 컬럼의 정체."""

    code: int
    name: str
    element: str | None = None
    is_active: bool = False
    dopant_role: DopantRole | None = None
    is_known: bool = True


def _dopant_pair(
    chem_code: int, element: str, role: DopantRole
) -> dict[int, Species]:
    """chem/active 쌍을 만든다. active = chem + 18 (실측으로 확인된 규칙).

    dopant_role 은 active 쪽에만 부여한다. Net doping 은 활성 농도로만 계산하며,
    chem 농도까지 더하면 이중 계산이 되기 때문이다.
    """
    return {
        chem_code: Species(
            code=chem_code, name=f"chem_{element}", element=element, is_active=False
        ),
        chem_code + _ACTIVE_OFFSET: Species(
            code=chem_code + _ACTIVE_OFFSET,
            name=f"active_{element}",
            element=element,
            is_active=True,
            dopant_role=role,
        ),
    }


_ACTIVE_OFFSET = 18

def _plain_pair(chem_code: int, element: str) -> dict[int, Species]:
    """역할을 정하지 않은 chem/active 쌍. 간격은 1 이다.

    확장 도펀트(GaAs 계열)는 고전 4종과 달리 active 코드가 바로 다음 번호다.

    **도너/억셉터를 붙이지 않는다.** Si·Ge 는 GaAs 에서 양쪽으로 작용할 수 있어
    (amphoteric) 단정하면 net doping 이 틀린다. 확인되기 전에는 이름만 준다 —
    지금도 계산에 들어가지 않으므로 후퇴가 아니다.
    """
    return {
        chem_code: Species(chem_code, f"chem_{element}", element=element),
        chem_code + 1: Species(
            chem_code + 1, f"active_{element}", element=element, is_active=True
        ),
    }


#: 도펀트가 아닌 컬럼. 이름의 근거는 상류 소스다 —
#: SUPREM4GS/upstream/src/include/impurity.h 의 #define 목록.
#: 예전에는 실측 파일에서 추정했고, 그래서 코드 24 를 net_doping 으로
#: 잘못 붙였다(실제로는 폴리실리콘 결정립 크기).
_DEFECTS_AND_FIELDS: dict[int, Species] = {
    0: Species(0, "vacancies"),
    1: Species(1, "interstitials"),
    6: Species(6, "electrons"),
    7: Species(7, "holes"),
    8: Species(8, "x_velocity"),
    9: Species(9, "y_velocity"),
    #: 산화제. `diffuse dryo2` 를 돌리면 실제로 담긴다.
    10: Species(10, "oxidant_dry"),
    11: Species(11, "oxidant_wet"),
    12: Species(12, "interstitial_traps"),
    13: Species(13, "gold"),
    14: Species(14, "potential"),
    #: 응력 성분. 해 변수는 아니지만 다시 계산하기 비싸 함께 저장된다.
    15: Species(15, "stress_xx"),
    16: Species(16, "stress_yy"),
    17: Species(17, "stress_xy"),
    #: 산화막 전하 모델용 세슘.
    18: Species(18, "cesium"),
    19: Species(19, "delta_interface_area"),
    #: **net doping 이 아니다.** impurity.h 의 `#define GRN 24`.
    24: Species(24, "poly_grain_size"),
    25: Species(25, "ptype_tracer"),
    #: 노드에 저장되지 않는다고 소스에 적혀 있다. 이름만 둔다.
    26: Species(26, "circuit"),
}

_SPECIES_BY_CODE: dict[int, Species] = {
    **_DEFECTS_AND_FIELDS,
    **_dopant_pair(2, "arsenic", DopantRole.DONOR),
    **_dopant_pair(3, "phosphorus", DopantRole.DONOR),
    **_dopant_pair(4, "antimony", DopantRole.DONOR),
    **_dopant_pair(5, "boron", DopantRole.ACCEPTOR),
    **_plain_pair(31, "beryllium"),
    **_plain_pair(33, "magnesium"),
    **_plain_pair(35, "selenium"),
    **_plain_pair(37, "isilicon"),
    **_plain_pair(39, "tin"),
    **_plain_pair(41, "germanium"),
    **_plain_pair(43, "zinc"),
    **_plain_pair(45, "carbon"),
    **_plain_pair(47, "generic"),
}


def resolve_species(code: int) -> Species:
    """코드를 Species 로 변환한다.

    사전에 없는 코드는 버리지 않고 `unknown_<코드>` 로 보존한다. 미확인 도펀트
    (beryllium=31, carbon=45 등)가 등장할 수 있고, 값을 조용히 버리면 데이터
    손실로 이어지기 때문이다.
    """
    known = _SPECIES_BY_CODE.get(code)
    if known is not None:
        return known
    return Species(code=code, name=f"unknown_{code}", is_known=False)


@dataclass(frozen=True, slots=True)
class SpeciesTable:
    """한 `.str` 파일의 컬럼 배치.

    `s` 라인의 코드 나열 순서가 곧 `n` 라인 값의 순서다. 이름→위치 조회와
    donor/acceptor 위치를 미리 계산해 둔다.
    """

    species: tuple[Species, ...]
    _index: Mapping[str, int]
    donor_positions: tuple[int, ...]
    acceptor_positions: tuple[int, ...]

    def __len__(self) -> int:
        return len(self.species)

    def position_of(self, name: str) -> int:
        try:
            return self._index[name]
        except KeyError:
            raise KeyError(
                f"{name!r} 는 이 구조에 없는 quantity 입니다. "
                f"사용 가능: {sorted(self._index)}"
            ) from None

    def has(self, name: str) -> bool:
        return name in self._index


def build_species_table(codes: Sequence[int]) -> SpeciesTable:
    """`s` 라인 코드 목록으로부터 컬럼 배치를 만든다."""
    species = tuple(resolve_species(code) for code in codes)
    return SpeciesTable(
        species=species,
        _index=MappingProxyType({s.name: i for i, s in enumerate(species)}),
        donor_positions=tuple(
            i for i, s in enumerate(species) if s.dopant_role is DopantRole.DONOR
        ),
        acceptor_positions=tuple(
            i for i, s in enumerate(species) if s.dopant_role is DopantRole.ACCEPTOR
        ),
    )
