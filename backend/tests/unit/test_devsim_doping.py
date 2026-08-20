"""도핑 이송 테스트.

DevSim 은 `NetDoping`(도너 − 억셉터, cm⁻³)을 노드마다 받는다. SUPREM 은 그 값을
컬럼으로 갖고 있지 않고 활성 도너·억셉터를 따로 적는다.

주의할 점 둘.

1. **점과 노드가 다르다.** 계면 점은 인접 물질 수만큼 값을 갖는다. 실리콘 쪽을
   물어야 하는데 산화막 쪽을 집으면 계면에서 도핑이 엉뚱해진다.
2. **활성 컬럼이 없을 수도 있다.** 그러면 `net_doping()` 이 0 만 돌려주어 도핑이
   없는 소자가 된다. 화학 농도로 떨어져야 한다.
"""

from pathlib import Path

import pytest

from app.devsim.doping import (
    DopingSource,
    doping_source,
    net_doping_by_point,
)
from app.str_parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def contacts():
    return parse_structure((FIXTURES / "2d_contacts.str").read_text())


@pytest.fixture
def boron_1d():
    return parse_structure((FIXTURES / "1d_boron.str").read_text())


class TestDopingSource:
    def test_prefers_active_when_present(self, contacts) -> None:
        assert doping_source(contacts.table) is DopingSource.ACTIVE

    def test_active_columns_really_exist_in_the_fixture(self, contacts) -> None:
        names = {species.name for species in contacts.table.species}
        assert "active_arsenic" in names
        assert "active_boron" in names


class TestNetDoping:
    def test_covers_every_point_of_the_region(self, contacts) -> None:
        silicon = next(r for r in contacts.regions if r.material == "silicon")
        points = {
            vertex
            for element in contacts.elements
            if element.region_id == silicon.id
            for vertex in element.vertices
        }
        values = net_doping_by_point(contacts, silicon.material_id)
        assert points <= set(values)

    def test_substrate_is_p_type(self, contacts) -> None:
        """기판은 boron 1e15 다. 깊은 곳은 음수(억셉터 우세)여야 한다."""
        silicon = next(r for r in contacts.regions if r.material == "silicon")
        values = net_doping_by_point(contacts, silicon.material_id)
        deep = max(
            (index for index in values),
            key=lambda index: contacts.coordinates[index].y,
        )
        assert values[deep] < 0
        assert abs(values[deep]) == pytest.approx(1.0e15, rel=0.5)

    def test_source_drain_is_n_type(self, contacts) -> None:
        """비소를 3e15 넣었다. 표면 쪽 어딘가는 양수여야 한다."""
        silicon = next(r for r in contacts.regions if r.material == "silicon")
        values = net_doping_by_point(contacts, silicon.material_id)
        surface = [
            value
            for index, value in values.items()
            if contacts.coordinates[index].y < 0.02
        ]
        assert max(surface) > 1.0e17

    def test_poly_gate_is_heavily_n_type(self, contacts) -> None:
        poly = next(r for r in contacts.regions if r.material == "poly")
        values = net_doping_by_point(contacts, poly.material_id)
        assert max(values.values()) > 1.0e18

    def test_reads_the_right_side_of_an_interface(self, contacts) -> None:
        """계면 점은 실리콘 쪽 값을 써야 한다.

        같은 좌표에 산화막 쪽 값이 따로 있고, 그쪽을 집으면 계면 한 줄이
        엉뚱한 농도가 된다.
        """
        silicon = next(r for r in contacts.regions if r.material == "silicon")
        oxide = next(r for r in contacts.regions if r.material == "oxide")
        si = net_doping_by_point(contacts, silicon.material_id)
        ox = net_doping_by_point(contacts, oxide.material_id)
        shared = set(si) & set(ox)
        assert shared, "계면 점이 있어야 이 시험이 의미가 있다"
        assert any(si[index] != ox[index] for index in shared)

    def test_unknown_material_gives_nothing(self, contacts) -> None:
        assert net_doping_by_point(contacts, 99) == {}

    def test_one_dimensional_structure_still_works(self, boron_1d) -> None:
        silicon = next(r for r in boron_1d.regions if r.material == "silicon")
        values = net_doping_by_point(boron_1d, silicon.material_id)
        assert values
        assert all(value < 0 for value in values.values())
