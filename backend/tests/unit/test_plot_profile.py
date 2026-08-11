"""깊이 프로파일.

축이 차원마다 다르다. 1D 파일은 **x** 가 깊이이고 y 는 항상 0 이다. 2D 파일은
**y** 가 깊이이고 x 는 가로 위치다. 실측으로 확인했다:

    1d_boron.str      x=[-0.075, 2.000]  y=[0, 0]
    2d_cmos_source.str x=[0, 4.000]      y=[-0.406, 3.000]

증착층은 깊이가 음수로 나온다(표면 위). 이걸 뒤집으면 산화막이 기판 아래에
그려진다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.plotting.profile import depth_profile, vertical_cut
from app.str_parser.parser import parse_structure

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="module")
def boron_1d():
    return parse_structure((FIXTURES / "1d_boron.str").read_text())


@pytest.fixture(scope="module")
def substrate_2d():
    return parse_structure((FIXTURES / "2d_substrate.str").read_text())


@pytest.fixture(scope="module")
def cmos_2d():
    return parse_structure((FIXTURES / "2d_cmos_source.str").read_text())


class TestOneDimensional:
    def test_uses_x_as_depth(self, boron_1d) -> None:
        profile = depth_profile(boron_1d, "chem_boron")
        depths = [point.depth for point in profile.points]

        assert min(depths) == pytest.approx(-0.075)
        assert max(depths) == pytest.approx(2.0)

    def test_points_are_sorted_by_depth(self, boron_1d) -> None:
        depths = [p.depth for p in depth_profile(boron_1d, "chem_boron").points]

        assert depths == sorted(depths)

    def test_deposited_layer_is_above_the_surface(self, boron_1d) -> None:
        """증착된 산화막은 깊이가 음수다. 부호를 뒤집으면 기판 아래로 그려진다."""
        profile = depth_profile(boron_1d, "chem_boron")
        shallowest = profile.points[0]

        assert shallowest.depth < 0
        assert shallowest.material == "oxide"

    def test_each_point_carries_its_material(self, boron_1d) -> None:
        materials = {p.material for p in depth_profile(boron_1d, "chem_boron").points}

        assert materials == {"oxide", "silicon"}

    def test_excludes_the_ambient_boundary(self, boron_1d) -> None:
        """ambient 는 기체이고 region 이 없다 — 시뮬레이션된 고체가 아니다.

        1d_boron.str 의 x=-0.075 에 ambient 노드가 하나 있는데 값이 1.0e8 짜리
        자리표시자다. 로그 축에서 이 점 하나가 축을 7제곱 아래로 끌어내려
        정작 봐야 할 프로파일이 납작해진다.
        """
        profile = depth_profile(boron_1d, "chem_boron")

        assert "ambient" not in {p.material for p in profile.points}
        assert min(profile.values) > 1e10

    def test_interface_keeps_both_materials(self, boron_1d) -> None:
        """계면에서는 같은 깊이에 물질별 값이 따로 있다. 하나로 뭉개면
        계면에서 값이 튄다."""
        profile = depth_profile(boron_1d, "chem_boron")
        at_surface = [p for p in profile.points if p.depth == pytest.approx(0.0)]

        assert {p.material for p in at_surface} == {"oxide", "silicon"}

    def test_rejects_unknown_quantity(self, boron_1d) -> None:
        with pytest.raises(KeyError):
            depth_profile(boron_1d, "chem_gallium")

    def test_rejects_2d_structure(self, substrate_2d) -> None:
        """2D 는 가로 위치를 정해야 프로파일이 결정된다."""
        with pytest.raises(ValueError, match="1D"):
            depth_profile(substrate_2d, "chem_boron")


class TestVerticalCut:
    def test_uses_y_as_depth(self, substrate_2d) -> None:
        cut = vertical_cut(substrate_2d, x=2.0, quantity="chem_boron")
        depths = [point.depth for point in cut.points]

        assert min(depths) == pytest.approx(0.0, abs=1e-6)
        assert max(depths) == pytest.approx(3.0, abs=1e-6)

    def test_points_are_sorted_by_depth(self, substrate_2d) -> None:
        depths = [p.depth for p in vertical_cut(substrate_2d, 2.0, "chem_boron").points]

        assert depths == sorted(depths)

    def test_uniform_substrate_has_a_flat_profile(self, substrate_2d) -> None:
        """균일 도핑 기판이므로 어느 깊이에서나 같은 값이어야 한다.

        보간이 틀리면 여기서 값이 흔들린다.
        """
        values = [p.value for p in vertical_cut(substrate_2d, 2.0, "chem_boron").points]

        assert min(values) == pytest.approx(max(values), rel=1e-6)

    def test_cut_at_a_mesh_line_works(self, substrate_2d) -> None:
        """격자선 위를 자르면 삼각형 변이 컷 라인과 겹친다. 이 경우를 빠뜨리면
        프로파일에 구멍이 생긴다."""
        cut = vertical_cut(substrate_2d, x=0.0, quantity="chem_boron")

        assert len(cut.points) > 1

    def test_cut_outside_the_domain_is_empty(self, substrate_2d) -> None:
        assert vertical_cut(substrate_2d, x=99.0, quantity="chem_boron").points == ()

    def test_interpolates_between_nodes(self, cmos_2d) -> None:
        """격자선 사이를 자르면 노드에 없던 깊이가 나와야 한다."""
        cut = vertical_cut(cmos_2d, x=0.317, quantity="chem_boron")
        node_depths = {round(c.y, 9) for c in cmos_2d.coordinates}
        cut_depths = {round(p.depth, 9) for p in cut.points}

        assert cut_depths - node_depths

    def test_values_stay_within_the_node_range(self, cmos_2d) -> None:
        """선형 보간 결과는 양 끝 노드 값 사이에 있어야 한다. 벗어나면 잘못된
        노드에서 값을 읽고 있다는 뜻이다."""
        cut = vertical_cut(cmos_2d, x=2.0, quantity="chem_boron")
        stored = [
            solution.value("chem_boron") for solution in cmos_2d.solutions
        ]

        assert min(cut.values) >= min(stored)
        assert max(cut.values) <= max(stored)

    def test_carries_material_per_point(self, cmos_2d) -> None:
        cut = vertical_cut(cmos_2d, x=2.0, quantity="chem_boron")

        assert {p.material for p in cut.points} >= {"silicon"}

    def test_rejects_1d_structure(self, boron_1d) -> None:
        with pytest.raises(ValueError, match="2D"):
            vertical_cut(boron_1d, x=0.0, quantity="chem_boron")


class TestInterfaceOrdering:
    """계면에서 같은 깊이에 놓인 두 점의 순서.

    재질명 알파벳순으로 정렬하면 물리적 적층과 어긋난다. CMOS 게이트에서 실제로
    겪었다 — x=2.0 의 적층은 oxide/poly/oxide/silicon 인데, 깊이 -0.00129 에서
    poly 가 끝나고 oxide 가 시작하는 자리를 알파벳순(oxide < poly)으로 놓는
    바람에 poly 층이 고립된 두 점으로 쪼개져 선이 그려지지 않았다.

    같은 깊이에서는 **앞 구간을 잇는 재질이 먼저** 와야 한다.
    """

    def test_material_runs_follow_the_stack(self, cmos_2d) -> None:
        cut = vertical_cut(cmos_2d, x=2.0, quantity="chem_boron")

        runs: list[str] = []
        for point in cut.points:
            if not runs or runs[-1] != point.material:
                runs.append(point.material)

        assert runs == ["oxide", "poly", "oxide", "silicon"]

    def test_each_layer_keeps_its_points_together(self, cmos_2d) -> None:
        """한 층의 점들이 흩어지면 선이 끊겨 그려진다."""
        cut = vertical_cut(cmos_2d, x=2.0, quantity="chem_boron")

        seen: dict[str, int] = {}
        runs = 0
        previous = None
        for point in cut.points:
            if point.material != previous:
                runs += 1
                seen[point.material] = seen.get(point.material, 0) + 1
            previous = point.material

        # poly 는 위아래가 산화막이라 한 번만 나타나야 한다.
        assert seen["poly"] == 1

    def test_depths_are_still_sorted(self, cmos_2d) -> None:
        """순서를 고쳐도 깊이 정렬은 깨지면 안 된다."""
        depths = [p.depth for p in vertical_cut(cmos_2d, 2.0, "chem_boron").points]

        assert depths == sorted(depths)
