"""2D 컨투어 페이로드와 물리량 해석."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.plotting.loader import clear_cache, load_structure
from app.plotting.quantities import NET_DOPING, available, value_of
from app.plotting.surface import build_surface
from app.str_parser.parser import parse_structure

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="module")
def cmos_2d():
    return parse_structure((FIXTURES / "2d_cmos_source.str").read_text())


@pytest.fixture(scope="module")
def boron_1d():
    return parse_structure((FIXTURES / "1d_boron.str").read_text())


class TestSurface:
    def test_covers_every_element(self, cmos_2d) -> None:
        surface = build_surface(cmos_2d, "chem_boron")

        assert len(surface.triangles) == len(cmos_2d.elements)

    def test_values_are_per_triangle_not_per_vertex(self, cmos_2d) -> None:
        """계면 정점은 물질에 따라 값이 다르다. 정점마다 값 하나만 두면 한쪽
        물질의 값이 반대쪽까지 번진다."""
        surface = build_surface(cmos_2d, "chem_boron")

        assert len(surface.values) == len(surface.triangles)
        assert all(len(triple) == 3 for triple in surface.values)

    def test_interface_vertex_gets_different_values_by_material(
        self, cmos_2d
    ) -> None:
        surface = build_surface(cmos_2d, "chem_boron")
        by_vertex: dict[int, set[float]] = {}
        for triangle, triple in zip(surface.triangles, surface.values):
            for vertex, value in zip(triangle, triple):
                by_vertex.setdefault(vertex, set()).add(value)

        # 계면 정점이 하나라도 물질별로 다른 값을 갖고 있어야 한다.
        assert any(len(values) > 1 for values in by_vertex.values())

    def test_carries_material_per_triangle(self, cmos_2d) -> None:
        surface = build_surface(cmos_2d, "chem_boron")

        assert set(surface.materials) == {"oxide", "poly", "silicon"}

    def test_coordinates_are_indexed_by_triangle_vertices(self, cmos_2d) -> None:
        surface = build_surface(cmos_2d, "chem_boron")
        highest = max(v for triangle in surface.triangles for v in triangle)

        assert highest < len(surface.x)
        assert len(surface.x) == len(surface.y)

    def test_reports_the_value_range(self, cmos_2d) -> None:
        low, high = build_surface(cmos_2d, "chem_boron").value_range

        assert low < high

    def test_rejects_1d_structure(self, boron_1d) -> None:
        with pytest.raises(ValueError, match="2D"):
            build_surface(boron_1d, "chem_boron")


class TestQuantities:
    def test_net_doping_is_computed_not_read(self, cmos_2d) -> None:
        """CMOS 파일에는 net_doping 컬럼(코드 24)이 실제로 있지만 쓸 수 없다.

        전기 시뮬레이션을 돌리지 않은 공정 결과에서는 도핑이 있어도 0 으로
        기록된다. 저장값을 그대로 보여주면 도핑이 없는 소자처럼 보인다.
        """
        assert cmos_2d.table.has(NET_DOPING)  # 컬럼은 존재한다

        computed = [value_of(s, NET_DOPING) for s in cmos_2d.solutions]
        stored = [s.value(NET_DOPING) for s in cmos_2d.solutions]

        assert any(value != 0.0 for value in computed)
        assert all(value == 0.0 for value in stored)

    def test_net_doping_is_donors_minus_acceptors(self, cmos_2d) -> None:
        solution = cmos_2d.solutions[0]

        assert value_of(solution, NET_DOPING) == solution.net_doping()

    def test_available_lists_the_stored_columns(self, boron_1d) -> None:
        names = available(boron_1d)

        assert "chem_boron" in names
        assert "active_boron" in names

    def test_available_offers_computed_net_doping(self, boron_1d) -> None:
        """저장 컬럼이 없어도 도펀트가 있으면 계산할 수 있다."""
        assert not boron_1d.table.has(NET_DOPING)

        assert NET_DOPING in available(boron_1d)

    def test_available_lists_net_doping_once(self, cmos_2d) -> None:
        """저장 컬럼과 계산값이 겹쳐 두 번 나오면 화면에 중복 항목이 뜬다."""
        assert available(cmos_2d).count(NET_DOPING) == 1


class TestLoaderCache:
    def test_parses_the_file(self, tmp_path) -> None:
        clear_cache()
        path = tmp_path / "a.str"
        path.write_text((FIXTURES / "1d_boron.str").read_text())

        assert load_structure(path).dimension == 1

    def test_reuses_the_parsed_result(self, tmp_path) -> None:
        clear_cache()
        path = tmp_path / "a.str"
        path.write_text((FIXTURES / "1d_boron.str").read_text())

        assert load_structure(path) is load_structure(path)

    def test_reparses_when_the_file_changes(self, tmp_path) -> None:
        """같은 잡을 다시 돌리면 같은 경로에 새 내용이 쓰인다. 경로만 키로 쓰면
        옛 결과를 계속 보여준다."""
        clear_cache()
        path = tmp_path / "a.str"
        path.write_text((FIXTURES / "1d_boron.str").read_text())
        first = load_structure(path)

        path.write_text((FIXTURES / "2d_substrate.str").read_text())
        second = load_structure(path)

        assert first.dimension == 1
        assert second.dimension == 2
