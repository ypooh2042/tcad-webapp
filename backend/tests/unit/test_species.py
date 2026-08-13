"""species 코드 사전 테스트.

`.str` 파일의 `s` 라인은 quantity 코드를 나열하며, 그 순서가 곧 `n` 라인 값의
순서다. 컬럼 위치는 파일마다 다르므로 코드 기반 매핑만이 안전하다.
근거는 SUPREM4GS/STR_FILE_FORMAT.md 참조.
"""

import pytest

from app.str_parser.species import (
    DopantRole,
    Species,
    resolve_species,
)


class TestKnownCodes:
    """3개 실측 파일로 교차 검증된 코드 사전."""

    @pytest.mark.parametrize(
        ("code", "name"),
        [
            (0, "vacancies"),
            (1, "interstitials"),
            (2, "chem_arsenic"),
            (3, "chem_phosphorus"),
            (4, "chem_antimony"),
            (5, "chem_boron"),
            (8, "x_velocity"),
            (9, "y_velocity"),
            (12, "interstitial_traps"),
            (14, "potential"),
            (19, "delta_interface_area"),
            (20, "active_arsenic"),
            (21, "active_phosphorus"),
            (22, "active_antimony"),
            (23, "active_boron"),
            # 코드 24 는 net doping 이 아니라 **폴리실리콘 결정립 크기**다.
            # 상류 소스가 정답이다: impurity.h 의 `#define GRN 24`.
            # 예전에는 net_doping 으로 잘못 이름 붙였고, 폴리가 없는 구조에서
            # 늘 0 이 나오는 것을 "전기 시뮬레이션을 안 돌려서"로 오해했다.
            (24, "poly_grain_size"),
        ],
    )
    def test_maps_verified_code_to_name(self, code: int, name: str) -> None:
        assert resolve_species(code).name == name

    @pytest.mark.parametrize(
        ("code", "name"),
        [
            (6, "electrons"),
            (7, "holes"),
            # 산화 중에 실제로 나온다. `diffuse dryo2` 를 돌리면 코드 10 이
            # 담기는데, 이름이 없어 화면에 unknown_10 경고가 떴다.
            (10, "oxidant_dry"),
            (11, "oxidant_wet"),
            (13, "gold"),
            (15, "stress_xx"),
            (16, "stress_yy"),
            (17, "stress_xy"),
            (18, "cesium"),
            (25, "ptype_tracer"),
            (31, "chem_beryllium"),
            (32, "active_beryllium"),
            (41, "chem_germanium"),
            (48, "active_generic"),
        ],
    )
    def test_maps_codes_read_from_upstream_header(
        self, code: int, name: str
    ) -> None:
        """상류 impurity.h 에 정의된 나머지 코드.

        레포에 소스가 들어온 뒤로는 실측으로 추정할 필요가 없다.
        SUPREM4GS/upstream/src/include/impurity.h 가 정답이다.
        """
        assert resolve_species(code).name == name

    def test_extended_dopants_pair_with_offset_one(self) -> None:
        """확장 도펀트는 chem/active 간격이 1 이다. 고전 4종의 +18 과 다르다."""
        assert resolve_species(43).name == "chem_zinc"
        assert resolve_species(44).name == "active_zinc"

    def test_extended_dopants_carry_no_dopant_role(self) -> None:
        """역할을 함부로 정하지 않는다.

        GaAs 계열에서 Si·Ge 는 양쪽으로 작용할 수 있어(amphoteric) 도너/억셉터를
        단정하면 net doping 이 틀린다. 이름만 붙이고 역할은 비워 둔다 — 지금도
        unknown 이라 계산에 안 들어가므로 후퇴가 아니다.
        """
        assert resolve_species(38).dopant_role is None
        assert resolve_species(42).dopant_role is None

    def test_unknown_code_is_preserved_not_dropped(self) -> None:
        """미확인 코드도 버리지 않고 보존해야 한다 (데이터 손실 방지)."""
        species = resolve_species(9999)
        assert species.name == "unknown_9999"
        assert species.is_known is False

    def test_known_code_is_flagged_known(self) -> None:
        assert resolve_species(5).is_known is True


class TestDopantRoles:
    """Net doping을 직접 계산하려면 donor/acceptor 구분이 필요하다.

    data/modelrc 에 `antimony donor`, `boron acceptor` 등으로 정의돼 있다.
    """

    @pytest.mark.parametrize("code", [20, 21, 22])
    def test_arsenic_phosphorus_antimony_are_donors(self, code: int) -> None:
        assert resolve_species(code).dopant_role is DopantRole.DONOR

    def test_boron_is_acceptor(self) -> None:
        assert resolve_species(23).dopant_role is DopantRole.ACCEPTOR

    @pytest.mark.parametrize("code", [0, 1, 12, 14, 24])
    def test_non_dopant_quantities_have_no_role(self, code: int) -> None:
        assert resolve_species(code).dopant_role is None

    def test_chem_concentration_is_not_used_for_net_doping(self) -> None:
        """Net doping은 active 농도로만 계산한다. chem 종은 role이 없어야 한다."""
        assert resolve_species(5).dopant_role is None  # chem_boron
        assert resolve_species(2).dopant_role is None  # chem_arsenic


class TestActiveChemPairing:
    """active = chem + 18 규칙 (antimony로 예측 후 실측 확인됨)."""

    @pytest.mark.parametrize(
        ("chem_code", "active_code"),
        [(2, 20), (3, 21), (4, 22), (5, 23)],
    )
    def test_active_code_is_chem_plus_18(self, chem_code: int, active_code: int) -> None:
        chem = resolve_species(chem_code)
        active = resolve_species(active_code)
        assert chem.element == active.element
        assert chem.is_active is False
        assert active.is_active is True


class TestImmutability:
    """전역 코딩 규칙: 불변 객체만 사용."""

    def test_species_is_frozen(self) -> None:
        species = resolve_species(5)
        with pytest.raises(Exception):
            species.name = "mutated"  # type: ignore[misc]

    def test_repeated_resolution_is_equal(self) -> None:
        assert resolve_species(5) == resolve_species(5)
