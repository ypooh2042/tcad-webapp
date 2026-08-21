"""소자 해석에 쓸 구조를 오래 보관한다.

잡 산출물은 유휴 스윕과 쿼터 스윕에 지워진다(`app/jobs/sweeper.py`). 그대로
쓰면 공정을 돌린 다음 날 해석하려 할 때마다 공정을 다시 돌려야 한다.

전부 보관하지는 않는다. 25단계 흐름이면 산출물이 25개 17MB 인데 그중 전극이
있는 것은 보통 마지막 한두 개뿐이다(`screening.analysable`).

같은 `.in` 을 다시 돌리면 그 `.in` 에서 나온 것은 **전부 지우고** 새로 채운다.
공정 코드를 고쳐 다시 돌렸는데 옛 구조가 목록에 남아 있으면, 어느 것이 지금
코드의 결과인지 구분할 수 없다.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.devsim.screening import analysable

logger = logging.getLogger(__name__)

#: 폴더 이름에 그대로 쓸 수 있는 글자. 나머지는 `-` 로 바꾼다.
_SAFE = re.compile(r"[^A-Za-z0-9가-힣._-]+")

#: 이름이 겹치지 않도록 뒤에 붙이는 해시 길이. 경로가 달라도 슬러그가 같아질
#: 수 있어서(`a/x.in` 과 `b/x.in`) 원본 경로에서 뽑아 붙인다.
_HASH_LENGTH = 8


@dataclass(frozen=True, slots=True)
class Placed:
    sequence: int
    filename: str
    path: str
    size_bytes: int


def slug_of(source_path: str) -> str:
    """`.in` 경로를 폴더 이름으로. 보관소 밖으로 나갈 수 없어야 한다.

    `..` 이나 `/` 가 남으면 사용자가 정한 경로로 파일을 쓰게 된다. 서버가 정한
    이름만 쓰는 것이 이 프로젝트의 규칙이다(`runner/sandbox.py` 와 같은 이유).
    """
    cleaned = _SAFE.sub("-", source_path).strip("-.") or "unnamed"
    # 해시는 늘 붙인다. 읽기 좋은 부분만 남기면 서로 다른 경로가 같은 이름이
    # 된다 — `mosfet/nmos.in` 과 `mosfet-nmos.in` 이 그렇다.
    digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    return f"{cleaned[:80]}-{digest}"


def _folder(root: Path, owner_id: int, source_path: str) -> Path:
    return Path(root) / f"user-{owner_id}" / slug_of(source_path)


def place_files(
    root: Path,
    owner_id: int,
    source_path: str,
    artifacts: Sequence[tuple[int, Path]],
) -> list[Placed]:
    """전극이 있는 구조만 보관소로 옮긴다. 그 `.in` 의 옛 것은 지운다.

    Args:
        artifacts: `(공정 단계 순서, 파일 경로)` 목록.
    """
    folder = _folder(root, owner_id, source_path)
    # **먼저 지운다.** 남겨 두면 이번 실행에서 사라진 단계가 목록에 계속 뜬다.
    shutil.rmtree(folder, ignore_errors=True)

    keep = [(sequence, path) for sequence, path in artifacts if analysable(path)]
    if not keep:
        return []

    folder.mkdir(parents=True, exist_ok=True)
    placed: list[Placed] = []
    for sequence, path in keep:
        target = folder / path.name
        try:
            shutil.copyfile(path, target)
        except OSError:
            logger.warning("구조를 보관하지 못했습니다: %s", path, exc_info=True)
            continue
        placed.append(
            Placed(
                sequence=sequence,
                filename=path.name,
                path=str(target),
                size_bytes=target.stat().st_size,
            )
        )
    return placed


def discard(root: Path, owner_id: int, source_path: str) -> None:
    """그 `.in` 에서 나온 보관본을 전부 지운다."""
    shutil.rmtree(_folder(root, owner_id, source_path), ignore_errors=True)
