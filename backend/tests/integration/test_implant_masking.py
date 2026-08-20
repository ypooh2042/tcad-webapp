"""마스크가 주입을 막는가.

**포토레지스트가 두 조각으로 남는 마스크 공정**을 재현한다. 창을 가운데
뚫으면 레지스트는 왼쪽 조각과 오른쪽 조각으로 끊어지는데, 시뮬레이터의
영역 자료구조는 영역 하나가 이어진 덩어리 하나라고 전제한다(build_reg 의
"a single simply connected region", skel_reg 의 닫힌 고리 하나). 조각난
영역은 한쪽만 기술되고 나머지는 없는 것이 된다.

없으면 마스크 노릇도 못 한다 — 주입은 영역 스켈레톤으로 세로 단면의 물질
층을 뽑아 정지능을 계산하기 때문이다. 실측으로 확인한 증상: 보이지 않는
조각 아래 실리콘이 뚫린 창과 **똑같이** 도핑되고, 그 조각 자신에는
아무것도 들어가지 않았다. 요소 기반 식각을 넣으면서 생긴 회귀였다 —
B-rep 식각은 sub_skel() 이 조각마다 영역을 새로 만들어 문제가 없었다.

실제 podman 컨테이너를 띄운다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.runner.runner import run_simulation
from app.str_parser.parser import parse_structure

pytestmark = pytest.mark.integration

#: 가운데 창을 뚫어 레지스트를 좌우 두 조각으로 끊는다.
MASKED_IMPLANT = """\
line x location=-3 spacing=0.05 tag=left
line x location=3 spacing=0.05 tag=right
line y loc=0 spacing=0.02 tag=surf
line y loc=0.5 spacing=0.05
line y loc=1.0 spacing=0.2 tag=bottom
region silicon xlo=left xhi=right ylo=surf yhi=bottom
bound exposed  xlo=left xhi=right ylo=surf  yhi=surf
bound backside xlo=left xhi=right ylo=bottom yhi=bottom
initialize boron conc=1.0e15 ori=100
deposit photoresist thick=0.4 divisions=4
etch photoresist start x=-1 y=0.2
etch continue x=1 y=0.2
etch continue x=1 y=-2
etch done x=-1 y=-2
implant arsenic energy=150 dose=4e12
structure out=implanted.str
"""

#: 배경값. `initialize` 가 넣는 값이고, 주입이 전혀 없었다는 뜻이다.
BACKGROUND = 1.0e5


def surface_arsenic(structure, x: float) -> float:
    """x 기둥에서 실리콘 최상단 노드의 비소 농도."""
    best: tuple[float, float] | None = None
    for node in structure.solutions:
        if node.material != "silicon":
            continue
        coord = structure.coordinates[node.coordinate_index]
        if abs(coord.x - x) > 0.05:
            continue
        index = node.table._index.get("chem_arsenic")
        value = node.values[index] if index is not None else 0.0
        if best is None or coord.y < best[0]:
            best = (coord.y, value)
    assert best is not None, f"x={x} 에 실리콘 노드가 없습니다"
    return best[1]


@pytest.fixture(scope="module")
def implanted(tmp_path_factory):
    """한 번만 돌린다 — 시험 넷이 같은 결과를 본다."""
    if shutil.which("podman") is None:
        pytest.skip("podman 이 없습니다")
    workdir: Path = tmp_path_factory.mktemp("masked-implant")
    result = run_simulation(MASKED_IMPLANT, workdir)
    assert result.succeeded, result.errors
    written = {path.name: path for path in result.structure_files}
    assert "implanted.str" in written, sorted(written)
    return parse_structure(written["implanted.str"].read_text())


class TestPhotoresistMasksImplant:
    def test_open_window_is_doped(self, implanted) -> None:
        """뚫린 창 아래는 실제로 주입되어야 한다 — 기준점."""
        assert surface_arsenic(implanted, 0.0) > 100 * BACKGROUND

    @pytest.mark.parametrize(
        ("x", "piece"),
        [(-2.0, "왼쪽"), (2.0, "오른쪽")],
    )
    def test_both_resist_pieces_mask(self, implanted, x: float, piece: str) -> None:
        """조각 **둘 다** 막아야 한다.

        회귀했을 때 막던 쪽은 스켈레톤이 기술한 한 조각뿐이었다. 그래서 한쪽만
        보는 시험은 통과해 버린다.
        """
        assert surface_arsenic(implanted, x) <= BACKGROUND, (
            f"{piece} 레지스트 조각이 주입을 막지 못했습니다"
        )

    def test_both_pieces_absorb_the_same_dose(self, implanted) -> None:
        """두 조각이 흡수한 선량이 서로 같아야 한다.

        실리콘이 깨끗한 것만으로는 부족하다 — 주입이 통째로 사라져도 같은
        결과가 나온다. 두 조각은 창을 사이에 둔 대칭이고 같은 두께이므로
        받는 선량도 같아야 한다. 회귀했을 때 보이지 않던 조각의 봉우리는
        보이던 조각의 1/10 이었다.

        창 가장자리는 세지 않는다 — 거기는 옆으로 퍼진 선량이 섞여 조각이
        제 몫을 못 받아도 값이 올라간다.
        """

        def peak(lo: float, hi: float) -> float:
            found = 0.0
            for node in implanted.solutions:
                if node.material != "photoresist":
                    continue
                coord = implanted.coordinates[node.coordinate_index]
                if not lo <= coord.x <= hi:
                    continue
                index = node.table._index.get("chem_arsenic")
                if index is not None:
                    found = max(found, node.values[index])
            return found

        left, right = peak(-3.0, -1.8), peak(1.8, 3.0)
        assert left > 1.0e16, f"왼쪽 조각에 선량이 없습니다 ({left:.3e})"
        assert 0.5 < right / left < 2.0, (
            f"두 조각이 받은 선량이 다릅니다: 왼쪽 {left:.3e}, 오른쪽 {right:.3e}"
        )
