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

from app.devsim.catalog import Placed, place_one

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


#: 소자 해석 탭에 처음부터 들어 있는 구조와, 그것을 만든 공정 코드.
#:
#: 작업공간에는 `.in` 만 들어간다. 그런데 소자 해석은 **실행 결과**를 입력으로
#: 받으므로, 예제를 한 번 돌리기 전에는 그 탭이 비어 있다. 처음 들어온 사람이
#: 거기서 아무것도 못 보는 것을 막으려고 결과도 함께 넣는다.
#:
#: 이름표를 `.in` 쪽에 맞춰 둔다. 사용자가 자기 `nmos.in` 을 돌리면 그 결과가
#: 이 자리를 대신한다 — 같은 `.in` 에서 나온 것은 갈아 끼우는 규칙(catalog)이
#: 그대로 적용된다.
STARTER_SOURCE = "nmos.in"
STARTER_STRUCTURE = "nmos.str"

#: 이 구조가 `nmos.in` 의 몇 번째 단계인지. 25단계 흐름의 마지막이다.
STARTER_SEQUENCE = 25


def seed_structure(structures_root: Path, owner_id: int) -> Placed | None:
    """예제 구조를 보관소에 넣는다. 실패하면 조용히 넘어간다.

    가입이 이것 때문에 막히면 안 된다 — 구조가 없어도 앱은 멀쩡히 돌아가고,
    사용자가 예제를 한 번 돌리면 채워진다.
    """
    source = EXAMPLES / STARTER_STRUCTURE
    try:
        return place_one(
            structures_root,
            owner_id=owner_id,
            source_path=STARTER_SOURCE,
            sequence=STARTER_SEQUENCE,
            path=source,
        )
    except OSError:
        logger.warning("예제 구조를 넣지 못했습니다", exc_info=True)
        return None
