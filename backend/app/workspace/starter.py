"""새 작업공간에 넣어 주는 예제.

처음 들어온 사람에게 빈 화면을 주면 무엇부터 해야 할지 알 수 없다. 실제로 도는
공정 흐름 하나가 들어 있으면 열어서 실행해 보는 것으로 시작할 수 있고, 문법도
거기서 배운다.

**예제는 패키지 안에 둔다.** 레포의 `SUPREM4GS/examples/` 를 런타임에 읽으면
그 트리가 없는 설치에서 조용히 아무것도 넣지 않는다. 대신 두 벌이 갈라지지
않도록 시험이 바이트 단위로 대조한다(tests/unit/test_workspace_starter.py).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

EXAMPLES = Path(__file__).parent / "examples"

#: 넣어 줄 파일들. 늘리려면 여기에만 더하면 된다.
SEED_FILES = ("nmos.in",)


def seed(root: Path) -> tuple[str, ...]:
    """예제를 작업공간 루트에 복사한다.

    **이미 있는 파일은 건드리지 않는다.** 사용자가 지운 예제가 되살아나면
    지울 방법이 없고, 고쳐 둔 것을 덮어쓰면 작업을 잃는다.

    Returns:
        실제로 넣은 파일 이름들.
    """
    placed: list[str] = []
    for name in SEED_FILES:
        source = EXAMPLES / name
        target = root / name
        if target.exists():
            continue
        try:
            shutil.copyfile(source, target)
        except OSError:
            # 예제를 못 넣는다고 가입이나 첫 요청이 실패할 이유는 없다.
            logger.warning("예제를 넣지 못했습니다: %s", name, exc_info=True)
            continue
        placed.append(name)
    return tuple(placed)
