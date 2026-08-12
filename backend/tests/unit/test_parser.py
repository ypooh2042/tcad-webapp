"""`.str` 구조 파일 파서 테스트.

골든 파일 3종으로 검증한다:
  - 1d_boron.str          exam1/boron.in 결과. 1D, boron 단일. species 6종.
  - 1d_multi_dopant.str   boron+phosphorus+antimony. species 10종. 코드 순서가
                          2D 파일과 다르다는 것을 보여주는 반례.
  - 2d_cmos_source.str    mosfet/CMOS.in 의 S/D implant 직후. 2D, 3도펀트,
                          4 region. species 14종.
"""

from pathlib import Path

import pytest

from app.str_parser import parse_structure
from app.str_parser.errors import StructureFormatError
from app.str_parser.materials import is_known_material, resolve_material

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def boron_1d():
    return parse_structure((FIXTURES / "1d_boron.str").read_text())


@pytest.fixture
def multi_1d():
    return parse_structure((FIXTURES / "1d_multi_dopant.str").read_text())


@pytest.fixture
def cmos_2d():
    return parse_structure((FIXTURES / "2d_cmos_source.str").read_text())


class TestHeader:
    def test_reads_version(self, boron_1d) -> None:
        assert boron_1d.version == "SUPREM-IV.GS B.9305"

    def test_detects_1d(self, boron_1d) -> None:
        assert boron_1d.dimension == 1

    def test_detects_2d(self, cmos_2d) -> None:
        assert cmos_2d.dimension == 2

    def test_reads_temperature_kelvin(self, boron_1d) -> None:
        """boron.in 은 diffuse temp=1100(°C) → 1373.0 K 로 기록된다."""
        assert boron_1d.temperature_k == pytest.approx(1373.0)


class TestCoordinates:
    def test_counts_1d_nodes(self, boron_1d) -> None:
        assert len(boron_1d.coordinates) == 43

    def test_counts_2d_nodes(self, cmos_2d) -> None:
        assert len(cmos_2d.coordinates) == 1392

    def test_first_coordinate_matches_file(self, boron_1d) -> None:
        first = boron_1d.coordinates[0]
        assert first.id == 1
        assert first.x == pytest.approx(0.0)

    def test_oxide_node_has_negative_x(self, boron_1d) -> None:
        """deposit oxide thick=0.075 → 표면 위쪽 노드가 x=-0.075 로 생긴다."""
        xs = [c.x for c in boron_1d.coordinates]
        assert min(xs) == pytest.approx(-0.075)

    def test_2d_domain_extent_matches_source(self, cmos_2d) -> None:
        """CMOS.in: line x 0~4, line y 0~3 (표면 위 증착층은 음수)."""
        xs = [c.x for c in cmos_2d.coordinates]
        assert max(xs) == pytest.approx(4.0)
        assert max(c.y for c in cmos_2d.coordinates) == pytest.approx(3.0)


class TestRegions:
    def test_1d_has_two_regions(self, boron_1d) -> None:
        assert len(boron_1d.regions) == 2

    def test_2d_has_four_regions(self, cmos_2d) -> None:
        assert len(cmos_2d.regions) == 4

    def test_material_names_resolved_from_r_lines(self, cmos_2d) -> None:
        """material_id→이름은 파일의 r 라인에서 동적으로 만들어야 한다.
        CMOS.in 은 silicon / oxide / poly / oxide 순으로 region 을 만든다."""
        assert [r.material for r in cmos_2d.regions] == [
            "silicon",
            "oxide",
            "poly",
            "oxide",
        ]


class TestSpeciesOrdering:
    """핵심: 컬럼 순서는 파일마다 다르다."""

    def test_1d_boron_species_order(self, boron_1d) -> None:
        assert [s.name for s in boron_1d.species] == [
            "chem_boron",
            "active_boron",
            "vacancies",
            "interstitials",
            "interstitial_traps",
            "potential",
        ]

    def test_multi_dopant_species_order(self, multi_1d) -> None:
        """도펀트가 전부 앞에 몰려 나오는 배치."""
        assert [s.name for s in multi_1d.species] == [
            "chem_boron",
            "active_boron",
            "chem_phosphorus",
            "active_phosphorus",
            "chem_antimony",
            "active_antimony",
            "vacancies",
            "interstitials",
            "interstitial_traps",
            "potential",
        ]

    def test_2d_species_order_differs_from_1d(self, cmos_2d) -> None:
        """같은 도펀트라도 공통 quantity 뒤에 P/As 가 붙는 다른 배치.
        위치 기반 하드코딩이 깨지는 것을 보여주는 회귀 테스트."""
        assert [s.name for s in cmos_2d.species] == [
            "chem_boron",
            "active_boron",
            "x_velocity",
            "y_velocity",
            "delta_interface_area",
            "vacancies",
            "interstitials",
            "interstitial_traps",
            "potential",
            "net_doping",
            "chem_phosphorus",
            "active_phosphorus",
            "chem_arsenic",
            "active_arsenic",
        ]


class TestSolutionValues:
    def test_value_lookup_is_by_name_not_position(self, cmos_2d) -> None:
        solution = cmos_2d.solutions[0]
        assert solution.value("chem_boron") is not None

    def test_boron_peak_matches_postmini_extraction(self, boron_1d) -> None:
        """postmini 가 뽑은 boron.B_CHEM 첫 실리콘 노드 값과 일치해야 한다."""
        silicon_solutions = [s for s in boron_1d.solutions if s.material == "silicon"]
        assert silicon_solutions[0].value("chem_boron") == pytest.approx(5.861329e18)

    def test_node_appears_once_per_adjacent_material(self, boron_1d) -> None:
        """계면 노드는 인접 물질마다 한 줄씩 존재한다."""
        by_coord: dict[int, int] = {}
        for s in boron_1d.solutions:
            by_coord[s.coordinate_index] = by_coord.get(s.coordinate_index, 0) + 1
        assert max(by_coord.values()) > 1

    def test_2d_solution_count(self, cmos_2d) -> None:
        assert len(cmos_2d.solutions) == 1566


class TestNetDoping:
    """코드 24(Net doping)의 저장값은 신뢰 불가 — 직접 계산해야 한다."""

    def test_stored_net_doping_is_zero_in_cmos(self, cmos_2d) -> None:
        """실제 도핑이 1e16 수준인데도 저장값은 0 — 이 사실을 회귀로 고정."""
        silicon = [s for s in cmos_2d.solutions if s.material == "silicon"]
        assert all(s.value("net_doping") == 0.0 for s in silicon[:50])

    def test_computed_net_doping_is_nonzero(self, cmos_2d) -> None:
        silicon = [s for s in cmos_2d.solutions if s.material == "silicon"]
        assert any(s.net_doping() != 0.0 for s in silicon)

    def test_boron_only_substrate_is_p_type(self, boron_1d) -> None:
        """boron 단일 도핑이므로 net doping 은 음수(acceptor)여야 한다."""
        silicon = [s for s in boron_1d.solutions if s.material == "silicon"]
        assert silicon[0].net_doping() == pytest.approx(-5.861329e18)

    def test_net_doping_sums_donors_minus_acceptors(self, multi_1d) -> None:
        silicon = [s for s in multi_1d.solutions if s.material == "silicon"]
        node = silicon[0]
        expected = (
            node.value("active_phosphorus")
            + node.value("active_antimony")
            - node.value("active_boron")
        )
        assert node.net_doping() == pytest.approx(expected)


class TestInvariants:
    """포맷이 조용히 틀리는 것을 막는 방어선."""

    def test_species_count_matches_declared(self, cmos_2d) -> None:
        assert len(cmos_2d.species) == 14
        for solution in cmos_2d.solutions:
            assert len(solution.values) == 14

    def test_rejects_species_count_mismatch(self) -> None:
        broken = "v X\nD 1 2 2\nc 1 0 0\nr 1 3\ns 3   5 23 0\nn 0 3 1.0 2.0\n"
        with pytest.raises(StructureFormatError, match="species"):
            parse_structure(broken)

    def test_rejects_declared_count_disagreeing_with_code_list(self) -> None:
        broken = "v X\nD 1 2 2\nc 1 0 0\nr 1 3\ns 5   5 23 0\n"
        with pytest.raises(StructureFormatError):
            parse_structure(broken)

    def test_warns_on_unknown_species_code(self) -> None:
        text = "v X\nD 1 2 2\nc 1 0 0\nr 1 3\ns 1   777\nn 0 3 1.0\n"
        structure = parse_structure(text)
        assert structure.species[0].name == "unknown_777"
        assert structure.warnings


class TestImmutability:
    def test_structure_is_frozen(self, boron_1d) -> None:
        with pytest.raises(Exception):
            boron_1d.version = "mutated"  # type: ignore[misc]


class TestMaterialIds:
    """`.str` 의 material_id 지도.

    번호는 추측할 수 없어 하나씩 증착해 확인했다. 각 물질만 올린 1D 구조에서
    silicon(3) 위에 새 region 이 하나 생기고, 그 id 가 그 물질의 번호다.

        deposit oxynitride  → r 2 5
        deposit aluminum    → r 2 6
        deposit photoresist → r 2 7
        deposit gaas        → r 2 8

    이름이 없으면 화면에서 회색 `unknown_6` 이 된다. 금속을 올린 구조가 통째로
    "모르는 재질" 로 보였다.
    """

    def test_names_every_material_the_simulator_can_deposit(self) -> None:
        assert [resolve_material(code) for code in range(9)] == [
            "ambient",
            "oxide",
            "nitride",
            "silicon",
            "poly",
            "oxynitride",
            "aluminum",
            "photoresist",
            "gaas",
        ]

    def test_still_admits_ignorance_beyond_that(self) -> None:
        # 조용히 다른 물질로 잘못 표시하는 것보다 모른다고 드러내는 편이 안전하다.
        assert resolve_material(99) == "unknown_99"
        assert not is_known_material(99)
