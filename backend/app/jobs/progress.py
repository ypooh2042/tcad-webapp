"""도는 잡이 어느 단계까지 갔는지.

**로그로는 알 수 없다.** stdout 을 파이프로 모아 실행이 끝난 뒤 한 번에
기록하므로, 도는 동안 DB 의 로그는 비어 있다. 그래서 진행을 알려면 다른
단서가 필요하고, 작업디렉토리에 떨어지는 `.str` 이 그것이다.

순서는 **소스에 적힌 `structure out=` 등장 순서**를 따른다. 파일 시각으로
정렬하면 안 되는 이유는 `runner/results.py` 의 `collect_structure_files` 에
적어 두었다 — 같은 타이머 틱 안에 쓰인 파일들은 `st_mtime_ns` 까지 같다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.runner.results import STRUCTURE_OUT_RE


@dataclass(frozen=True, slots=True)
class Progress:
    """공정 흐름에서 지금까지 끝난 지점."""

    done: int
    total: int
    #: 마지막으로 저장된 구조 파일 이름. 아직 하나도 없으면 None.
    latest: str | None


def expected_outputs(source: str) -> tuple[str, ...]:
    """소스가 만들겠다고 적어 둔 구조 파일 이름들. 등장 순서대로, 중복 없이.

    같은 이름을 두 번 쓰면 두 번째가 첫 번째를 덮어쓴다. 셀 수 있는 것은
    파일 하나뿐이므로 중복은 접는다 — 그러지 않으면 파일 하나가 생긴 순간
    진행이 두 칸 뛴다.
    """
    names: list[str] = []
    for match in STRUCTURE_OUT_RE.finditer(source):
        name = Path(match.group(1)).name
        if name not in names:
            names.append(name)
    return tuple(names)


def scan_progress(workdir: Path, source: str) -> Progress | None:
    """지금까지 저장된 단계를 센다.

    Returns:
        Progress. 소스에 구조 저장 명령이 없거나 작업디렉토리를 읽을 수 없으면
        None — 셀 근거가 없는데 0/0 을 지어내면 화면이 거짓을 말하게 된다.
    """
    expected = expected_outputs(source)
    if not expected:
        return None

    try:
        present = {
            entry.name
            for entry in Path(workdir).iterdir()
            if entry.name.endswith(".str")
        }
    except OSError:
        # 청소된 잡이 여기로 온다. 디렉토리가 없으면 "0단계"가 아니라 **모른다**
        # 이다. 0 으로 답하면 화면이 이미 끝난 잡을 시작 전으로 보여준다.
        return None

    done = 0
    latest: str | None = None
    for index, name in enumerate(expected, start=1):
        if name in present:
            done, latest = index, name

    return Progress(done=done, total=len(expected), latest=latest)
