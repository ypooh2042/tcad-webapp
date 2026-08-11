"""시뮬레이션 실행 결과와 로그 해석.

중요: **종료 코드는 성공 여부를 알려주지 않는다.** SUPREM4GS 는 커맨드 오류가
있어도 exit 0 으로 끝난다(exam1/boron.in 의 잘못된 `option plot.out=` 줄에서
"errors detected on command input" 을 출력하고도 종료 코드는 0이었다).
따라서 오류 판정은 표준출력을 읽어서 해야 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: 시뮬레이터가 커맨드 오류를 알릴 때 쓰는 문구들. 종료 코드로는 안 잡힌다.
_ERROR_PATTERNS = (
    re.compile(r"^errors detected on command input", re.IGNORECASE),
    re.compile(r"^parameter .* does not exist", re.IGNORECASE),
    re.compile(r"^ambiguous parameter", re.IGNORECASE),
    re.compile(r"^unknown command", re.IGNORECASE),
    re.compile(r"not found$"),  # 셸 fall-through: 오타가 셸로 넘어간 경우
)


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """한 번의 시뮬레이션 실행 결과."""

    exit_code: int
    #: stdout 과 stderr 를 합친 실행 로그. 시뮬레이터 오류가 stderr 로 나가므로
    #: 분리하면 사용자가 빈 로그만 보게 된다.
    log: str
    timed_out: bool
    #: 생성된 `.str` 구조 파일. 공정 단계 순서(수정시각)대로 정렬돼 있다.
    structure_files: tuple[Path, ...]
    #: 로그에서 찾은 오류 줄. 비어 있어야 정상이다.
    errors: tuple[str, ...]

    @property
    def succeeded(self) -> bool:
        """종료 코드가 아니라 오류 줄과 타임아웃으로 판정한다."""
        return not self.timed_out and not self.errors and self.exit_code == 0


def extract_errors(log: str) -> tuple[str, ...]:
    """로그(stdout+stderr)에서 오류 줄만 골라낸다."""
    return tuple(
        line.strip()
        for line in log.splitlines()
        if any(pattern.search(line.strip()) for pattern in _ERROR_PATTERNS)
    )


def collect_structure_files(workdir: Path) -> tuple[Path, ...]:
    """생성된 `.str` 파일을 공정 단계 순서로 모은다.

    CMOS 예제처럼 `structure out=` 을 여러 번 쓰면 단계별 파일이 순서대로
    쌓인다. 이름순이 아니라 생성 순서여야 공정 흐름과 일치한다.
    """
    return tuple(sorted(workdir.glob("*.str"), key=lambda p: p.stat().st_mtime))
