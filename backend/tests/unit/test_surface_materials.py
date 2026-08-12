"""재질만 보는 단면.

물리량 단면과 결정적으로 다른 점은 **아무 요소도 버리지 않는다**는 것이다.
값을 칠할 때는 그 물질에 해가 없는 요소를 빼야 계면에서 값이 번지지 않지만,
재질을 보여줄 때 층이 빠지면 그림이 거짓말을 한다 — 없는 층을 없다고 읽는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.plotting.surface import build_surface
from app.str_parser.parser import parse_structure

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="module")
def cmos_2d():
    return parse_structure((FIXTURES / "2d_cmos_source.str").read_text())


@pytest.fixture(scope="module")
def boron_1d():
    return parse_structure((FIXTURES / "1d_boron.str").read_text())


class TestMaterialOnly:
    def test_keeps_every_element(self, cmos_2d):
        """어떤 물리량을 고르든 재질 보기는 요소를 다 남긴다.

        물리량 단면은 해가 없는 요소를 버린다. 재질 보기가 같은 규칙을 따르면
        층이 통째로 사라질 수 있다.
        """
        surface = build_surface(cmos_2d, None)

        assert len(surface.triangles) == len(cmos_2d.elements)

    def test_shows_every_material_in_the_structure(self, cmos_2d):
        every = {region.material for region in cmos_2d.regions}

        surface = build_surface(cmos_2d, None)

        assert set(surface.materials) == every

    def test_carries_one_material_per_triangle(self, cmos_2d):
        # 프론트가 삼각형마다 색을 고르려면 길이가 같아야 한다.
        surface = build_surface(cmos_2d, None)

        assert len(surface.materials) == len(surface.triangles)

    def test_carries_no_values(self, cmos_2d):
        # 칠할 값이 없다. 0 을 채워 넣으면 색 범위가 뒤틀린다.
        surface = build_surface(cmos_2d, None)

        assert surface.values == ()

    def test_value_range_is_empty(self, cmos_2d):
        surface = build_surface(cmos_2d, None)

        assert surface.value_range == (0.0, 0.0)

    def test_quantity_is_blank(self, cmos_2d):
        surface = build_surface(cmos_2d, None)

        assert surface.quantity == ""

    def test_coordinates_match_the_value_view(self, cmos_2d):
        """같은 구조를 같은 자리에 그려야 한다. 좌표가 다르면 물리량 보기와
        재질 보기를 오갈 때 그림이 튄다."""
        by_value = build_surface(cmos_2d, "chem_boron")
        by_material = build_surface(cmos_2d, None)

        assert by_material.x == by_value.x
        assert by_material.y == by_value.y

    def test_still_refuses_1d(self, boron_1d):
        with pytest.raises(ValueError):
            build_surface(boron_1d, None)


class TestValueViewUnchanged:
    def test_still_drops_elements_without_a_solution(self, cmos_2d):
        # 재질 보기를 넣느라 물리량 보기의 규칙이 바뀌면 계면 값이 번진다.
        surface = build_surface(cmos_2d, "chem_boron")

        assert len(surface.values) == len(surface.triangles)

    def test_still_reports_the_quantity(self, cmos_2d):
        assert build_surface(cmos_2d, "chem_boron").quantity == "chem_boron"
