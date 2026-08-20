"""도핑 기울기를 보고 목표 크기를 정한다.

기하만 보고 성기게 만들면 도핑이 가파른 자리에서 값이 뭉개진다 — 실측으로
비소 총선량이 13.6% 어긋났다. 접합 깊이가 달라지는 크기라 받아들일 수 없다.

그래서 **한 요소를 건너며 농도가 바뀌는 정도**를 기준으로 크기를 정한다.
가파른 곳은 촘촘하게, 완만한 곳은 성기게. 현대 도구가 하는 해 적응 격자다.
"""

from __future__ import annotations

from pathlib import Path

from app.remesh.sizefield import node_sizes
from app.str_parser.parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return parse_structure((FIXTURES / name).read_text())


class TestNodeSizes:
    def test_gives_every_point_a_size(self) -> None:
        structure = load("2d_cmos_source.str")

        sizes = node_sizes(structure, floor=1e-3, ceiling=1.0)

        assert len(sizes) == len(structure.coordinates)
        assert all(v > 0 for v in sizes)

    def test_respects_the_floor_and_ceiling(self) -> None:
        structure = load("2d_cmos_source.str")

        sizes = node_sizes(structure, floor=5e-3, ceiling=0.05)

        assert min(sizes) >= 5e-3
        assert max(sizes) <= 0.05

    def test_refines_where_doping_changes_fast(self) -> None:
        """가파른 자리가 완만한 자리보다 촘촘해야 한다. 이게 이 모듈의 전부다."""
        structure = load("2d_cmos_source.str")
        sizes = node_sizes(structure, floor=1e-4, ceiling=1.0)

        # 각 점의 이웃 대비 농도 변화폭을 재서, 큰 쪽과 작은 쪽을 비교한다.
        import math

        c = structure.coordinates
        material = {r.id: r.material_id for r in structure.regions}
        names = [s.name for s in structure.species if s.name.startswith("chem_")]
        swing: dict[int, float] = {}
        for e in structure.elements:
            m = material.get(e.region_id)
            if m is None:
                continue
            values = []
            for i in e.vertices:
                try:
                    row = structure.solution_at(i, m)
                except KeyError:
                    values = []
                    break
                values.append(max(row.value(n) for n in names))
            if len(values) != 3 or min(values) <= 0:
                continue
            span = math.log10(max(values)) - math.log10(min(values))
            for i in e.vertices:
                swing[i] = max(swing.get(i, 0.0), span)

        steep = [i for i, v in swing.items() if v > 0.5]
        flat = [i for i, v in swing.items() if v < 0.01]
        assert steep and flat

        assert sum(sizes[i] for i in steep) / len(steep) < sum(
            sizes[i] for i in flat
        ) / len(flat)

    def test_handles_a_structure_without_doping(self) -> None:
        """농도가 전부 같으면 기울기가 0 이다. 0 으로 나누면 안 된다."""
        structure = load("2d_substrate.str")

        sizes = node_sizes(structure, floor=1e-3, ceiling=0.5)

        assert all(1e-3 <= v <= 0.5 for v in sizes)
