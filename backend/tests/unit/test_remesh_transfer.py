"""옛 메시의 물성값을 새 메시로 옮기기.

새 점은 옛 메시 어딘가에 놓여 있다. 그 삼각형의 세 노드 값을 무게중심 좌표로
섞어 준다(P1 보간).

**물질을 반드시 맞춰야 한다.** 계면 점은 물질마다 값이 다르다 — CMOS 예제의
한 지점에서 산화막 쪽 1.03e17, 실리콘 쪽 2.07e16 이다. 물질을 무시하고
가까운 값을 집으면 계면에서 농도가 튄다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.remesh.transfer import Sampler
from app.str_parser.parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def structure():
    return parse_structure((FIXTURES / "2d_cmos_source.str").read_text())


class TestSampler:
    def test_reproduces_values_at_existing_points(self, structure) -> None:
        """옛 점 자리에서는 옛 값이 그대로 나와야 한다. 보간의 최소 조건이다."""
        sampler = Sampler(structure)
        material = structure.regions[0].material_id
        found = 0

        for node in structure.solutions[:200]:
            if node.material_id != material:
                continue
            c = structure.coordinates[node.coordinate_index]
            got = sampler.at(c.x, c.y, material)
            assert got is not None
            for a, b in zip(got, node.values):
                assert a == pytest.approx(b, rel=1e-6, abs=1e-30)
            found += 1

        assert found, "확인할 노드를 못 찾았다"

    def test_interpolates_between_points(self, structure) -> None:
        """두 점 사이 중간에서는 두 값 사이가 나와야 한다."""
        sampler = Sampler(structure)
        element = structure.elements[0]
        material = next(
            r.material_id for r in structure.regions if r.id == element.region_id
        )
        a, b, c = (structure.coordinates[i] for i in element.vertices)
        mid = ((a.x + b.x + c.x) / 3, (a.y + b.y + c.y) / 3)

        got = sampler.at(mid[0], mid[1], material)

        assert got is not None
        corners = [sampler.at(p.x, p.y, material) for p in (a, b, c)]
        for i, value in enumerate(got):
            lo = min(v[i] for v in corners)
            hi = max(v[i] for v in corners)
            assert lo - 1e-30 <= value <= hi + 1e-30

    def test_returns_none_outside_the_material(self, structure) -> None:
        # 그 물질이 없는 자리를 물으면 모른다고 해야 한다. 아무 값이나 주면
        # 없는 층이 생긴다.
        sampler = Sampler(structure)

        assert sampler.at(-1e6, -1e6, structure.regions[0].material_id) is None

    def test_finds_points_far_from_the_first_element(self, structure) -> None:
        """색인이 없으면 큰 구조에서 못 견딘다. 멀리 있는 점도 찾아야 한다."""
        sampler = Sampler(structure)
        last = structure.elements[-1]
        material = next(
            r.material_id for r in structure.regions if r.id == last.region_id
        )
        a, b, c = (structure.coordinates[i] for i in last.vertices)

        got = sampler.at((a.x + b.x + c.x) / 3, (a.y + b.y + c.y) / 3, material)

        assert got is not None


class TestNearestFallback:
    """경계를 단순화하면 새 점이 옛 물질 밖으로 조금 벗어난다.

    단순화 허용오차만큼(1 nm) 어긋날 뿐이므로, 가장 가까운 삼각형의 값을 쓰면
    된다. 없다고 포기하면 재메시 자체가 실패한다.
    """

    def test_samples_just_outside_the_material(self, structure) -> None:
        sampler = Sampler(structure)
        material = structure.regions[0].material_id
        node = next(s for s in structure.solutions if s.material_id == material)
        c = structure.coordinates[node.coordinate_index]

        # 경계에서 아주 조금 벗어난 자리.
        got = sampler.at(c.x + 1e-7, c.y + 1e-7, material, reach=1e-6)

        assert got is not None

    def test_still_refuses_a_faraway_point(self, structure) -> None:
        sampler = Sampler(structure)

        assert sampler.at(-1e6, -1e6, structure.regions[0].material_id, reach=1e-6) is None
