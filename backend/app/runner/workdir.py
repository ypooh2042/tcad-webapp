"""잡 작업 디렉토리 관리.

컨테이너에 붙는 /work 는 호스트 파일시스템 bind mount 다. 실제로 확인했다:
잡 하나가 몇 초 만에 호스트 디스크에 200MB 를 썼고 아무도 막지 않았다.
타임아웃 600초 × NVMe 쓰기 속도면 여유 공간을 전부 채울 수 있고, 그러면 이
홈서버에서 같이 도는 다른 서비스까지 함께 죽는다.

/tmp 는 컨테이너 안에서 tmpfs 64m 로 묶여 있지만 /work 는 그럴 수 없다 —
tmpfs 로 만들면 산출물이 컨테이너와 함께 사라진다.

그래서 두 겹으로 막는다:
  1. 실행 중: 주기적으로 크기를 재서 넘으면 잡을 죽인다(runner 가 호출).
  2. 실행 후: 산출물이 아닌 파일을 지운다. 사용자가 만든 임의 파일을 보관할
     이유가 없다.

완벽한 차단은 파일시스템 쿼터(XFS project quota 등)로만 가능하다. 여기서는 그
전제를 두지 않고, 피해 규모를 상한 이하로 묶는 것을 목표로 한다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

#: SUPREM 실행이 남기는 산출물. 이것만 화면에서 쓴다.
STRUCTURE_SUFFIXES = frozenset({".str"})

#: 소자 해석이 남기는 산출물. 곡선 데이터와, 도중에 끊겼을 때 되살릴 중간 기록.
#:
#: 확장자가 아니라 **이름**으로 고른다. 같은 디렉토리에 있는 `device.json` 은
#: 메시 전체가 든 5 MB 짜리 입력이라 남길 이유가 없는데, 확장자로 거르면 함께
#: 살아남는다. 구조 파일(`.str`)도 뺀다 — 원본 잡에 그대로 있다.
DEVSIM_ARTIFACTS = frozenset({"iv.json", "iv.jsonl"})


class WorkdirTooLarge(Exception):
    """작업 디렉토리가 상한을 넘었다."""


def directory_size(path: Path) -> int:
    """디렉토리가 차지하는 바이트 수.

    심볼릭 링크는 따라가지 않는다. 사용자 코드가 `/` 를 가리키는 링크를 만들어
    두면 호스트 전체를 세게 되고, 그것만으로도 잡이 몇 분씩 멈춘다.
    """
    total = 0
    for entry in path.rglob("*"):
        if entry.is_symlink() or not entry.is_file():
            continue
        try:
            total += entry.stat().st_size
        except OSError:
            # 세는 도중 사라졌다. 실행 중인 잡이 파일을 지우는 것은 정상이다.
            continue
    return total


def enforce_size_limit(path: Path, limit_bytes: int) -> None:
    """상한을 넘었으면 예외를 던진다.

    Raises:
        WorkdirTooLarge: 넘었을 때. 호출부는 잡을 실패로 기록해야 한다.
    """
    size = directory_size(path)
    if size > limit_bytes:
        raise WorkdirTooLarge(
            f"작업 디렉토리가 상한을 넘었습니다: "
            f"{_human(size)} > {_human(limit_bytes)}"
        )


def _human(size: int) -> str:
    """읽을 수 있는 크기. MB 로만 찍으면 작은 값이 전부 0.0MB 가 된다."""
    for unit, threshold in (("MB", 1_048_576), ("KB", 1024)):
        if size >= threshold:
            return f"{size / threshold:.1f}{unit}"
    return f"{size}B"


def prune_workdir(
    path: Path,
    keep: frozenset[str] = STRUCTURE_SUFFIXES,
    keep_names: frozenset[str] = frozenset(),
) -> int:
    """산출물만 남기고 나머지를 지운다.

    잡 종류마다 산출물이 다르다. 확장자(`keep`) 로도, 정확한 이름(`keep_names`)
    으로도 고를 수 있게 둘 다 받는다 — 소자 해석은 같은 `.json` 중에서도
    결과만 남기고 입력은 버려야 한다.

    Returns:
        비운 바이트 수.
    """
    freed = 0

    for entry in sorted(path.iterdir(), reverse=True):
        if entry.is_dir() and not entry.is_symlink():
            freed += directory_size(entry)
            shutil.rmtree(entry, ignore_errors=True)
            continue

        if entry.is_symlink() or (
            entry.suffix not in keep and entry.name not in keep_names
        ):
            try:
                freed += entry.stat().st_size if entry.is_file() else 0
                entry.unlink()
            except OSError:
                continue

    return freed
