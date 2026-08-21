"""해석할 수 있는 구조인지 가려낸다.

전극이 없는 구조를 목록에 올려 두면 사용자는 고른 뒤에야 "전극이 없습니다"를
본다. 25단계짜리 흐름에서 어느 단계부터 되는지 하나씩 눌러 보게 된다.

기준은 하나다: **알루미늄이 실리콘이나 폴리실리콘에 닿았는가.** 금속이
산화막에만 닿은 것은 전극이 아니다 — 전위는 걸려도 전류가 드나들 곳이 없다.

두 단계로 본다. 파싱은 파일 하나에 100 ms 가까이 걸리고 25단계 흐름이면 그것이
스물다섯 번이라 목록을 여는 것만으로 몇 초가 든다. 먼저 글자만 훑어 알루미늄
영역이 있는 파일로 좁힌 뒤(실측: 26개 17MB 를 76 ms) 그것만 제대로 읽는다.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.devsim.electrodes import METAL, ContactKind, detect_electrodes
from app.plotting.loader import load_structure
from app.str_parser.errors import StructureFormatError
from app.str_parser.materials import material_id_of
from app.str_parser.models import Structure

logger = logging.getLogger(__name__)

#: 알루미늄 영역을 선언하는 줄. `r <영역번호> <재질번호>` 이고 알루미늄은 6 이다.
#:
#: 삼각형(`t`) 줄에도 6 은 얼마든지 나오므로 줄 머리를 붙잡아야 한다. `\s*$` 앞에
#: `\r?` 를 두는 대신 `\s` 로 받는다 — 윈도우 줄바꿈이 섞인 파일이 실제로 있다.
_METAL_REGION = re.compile(
    rb"^r\s+\d+\s+%d\s*$" % material_id_of(METAL), re.MULTILINE
)


def mentions_metal(raw: bytes) -> bool:
    """알루미늄 영역을 선언한 파일인가. 읽지 않고 글자만 훑는다."""
    return _METAL_REGION.search(raw) is not None


def has_driveable_contact(structure: Structure) -> bool:
    """전류가 드나들 수 있는 접촉이 있는가.

    산화막에만 닿은 금속은 세지 않는다. 게이트처럼 전위만 거는 접촉은 그것만
    있어서는 소자가 되지 않는다.
    """
    return any(
        electrode.kind is ContactKind.SEMICONDUCTOR
        for electrode in detect_electrodes(structure)
    )


def analysable(path: Path) -> bool:
    """이 `.str` 로 소자 해석을 걸 수 있는가.

    파일이 없거나 읽히지 않아도 예외를 내지 않는다. 목록을 만들다 터지면 멀쩡한
    구조까지 함께 사라진다 — 산출물은 청소로 없어질 수 있다.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    if not mentions_metal(raw):
        return False
    try:
        return has_driveable_contact(load_structure(path))
    except (OSError, StructureFormatError, ValueError):
        logger.info("구조를 읽지 못해 해석 대상에서 뺍니다: %s", path, exc_info=True)
        return False
