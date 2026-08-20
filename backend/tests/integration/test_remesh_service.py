"""메시 다시 짜기 — 컨테이너까지 포함한 전 구간.

gmsh 를 실제로 띄운다. 단위 시험은 각 조각만 보므로, 조각이 다 맞는데 전체가
안 도는 경우를 여기서 잡는다.

**형상은 변하지 않아야 한다.** 경계와 계면을 제약으로 고정하기 때문이다.
물질별 면적이 그 직접 증거다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.remesh.service import remesh
from app.str_parser.parser import parse_structure

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent.parent / "fixtures"


def require_image() -> None:
    if shutil.which("podman") is None:
        pytest.skip("podman 이 없습니다")


def areas(structure) -> dict[str, float]:
    c = structure.coordinates
    material = {r.id: r.material for r in structure.regions}
    out: dict[str, float] = {}
    for e in structure.elements:
        p = [(c[i].x, c[i].y) for i in e.vertices]
        a = abs(
            (p[1][0] - p[0][0]) * (p[2][1] - p[0][1])
            - (p[2][0] - p[0][0]) * (p[1][1] - p[0][1])
        ) / 2
        key = material.get(e.region_id, "?")
        out[key] = out.get(key, 0.0) + a
    return out


class TestRemesh:
    def test_produces_a_readable_structure(self) -> None:
        require_image()
        source = (FIXTURES / "2d_cmos_source.str").read_text()

        result = remesh(source)

        assert parse_structure(result.text).elements

    def test_keeps_every_material_area(self) -> None:
        """형상이 그대로라는 직접 증거."""
        require_image()
        source = (FIXTURES / "2d_cmos_source.str").read_text()

        rebuilt = parse_structure(remesh(source).text)

        before = areas(parse_structure(source))
        after = areas(rebuilt)
        assert set(after) == set(before)
        for material, value in before.items():
            assert after[material] == pytest.approx(value, rel=1e-6)

    def test_keeps_the_boundary_conditions(self) -> None:
        # 노출면·뒷면을 잃으면 산화가 엉뚱해진다.
        require_image()
        source = (FIXTURES / "2d_cmos_source.str").read_text()

        rebuilt = parse_structure(remesh(source).text)

        def kinds(s):
            return {n for e in s.elements for n in e.neighbors if n < 0}

        assert kinds(rebuilt) == kinds(parse_structure(source))

    def test_refuses_a_one_dimensional_structure(self) -> None:
        """1 차원은 다시 짤 이유도 없고 기하가 다르다. 조용히 망가뜨리지 않는다."""
        require_image()

        with pytest.raises(ValueError, match="2 차원"):
            remesh((FIXTURES / "1d_boron.str").read_text())
