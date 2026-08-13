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

#: 시뮬레이터가 실패를 알릴 때 쓰는 문구들. 종료 코드로는 안 잡힌다.
#:
#: 목록은 suprem 바이너리의 문자열 테이블에서 뽑았다(`strings -n 6 suprem`).
#: 추측으로 채우면 반드시 빠뜨리는 것이 생기고, 빠뜨린 문구 하나가 "아무것도
#: 만들지 못한 실행"을 성공으로 기록한다. 실제로 메시 관련 문구들이 빠져 있어
#: No mesh defined! 가 난 잡이 SUCCEEDED 로 남고 사용자는 빈 그래프만 봤다.
_ERROR_PATTERNS = (
    # 커맨드 해석 실패
    re.compile(r"^errors detected on command input", re.IGNORECASE),
    re.compile(r"^parameter .* does not exist", re.IGNORECASE),
    re.compile(r"^ambiguous parameter", re.IGNORECASE),
    re.compile(r"^the command is ambiguous", re.IGNORECASE),
    re.compile(r"^unknown command", re.IGNORECASE),
    re.compile(r"^no command defined for name", re.IGNORECASE),
    re.compile(r"^illegal input", re.IGNORECASE),
    re.compile(r"^bad expression:", re.IGNORECASE),
    re.compile(r"^no character string given for", re.IGNORECASE),
    # 메시·구조를 못 만든 경우. 이후 모든 커맨드가 빈 구조 위에서 돌아
    # 산출물은 생기지만 내용이 없다.
    re.compile(r"^no mesh defined", re.IGNORECASE),
    re.compile(r"^user mesh data not given", re.IGNORECASE),
    re.compile(r"^no value specified for", re.IGNORECASE),
    re.compile(r"^no material specified for region", re.IGNORECASE),
    re.compile(r"^no region yet", re.IGNORECASE),
    re.compile(r"^no orientation given", re.IGNORECASE),
    re.compile(r"^no such . tag:", re.IGNORECASE),
    # 셸 fall-through: 인식하지 못한 첫 단어가 /bin/bash 로 넘어간 경우.
    #
    # 메시지 본문("command not found")은 로케일에 따라 번역되므로 문구로 찾으면
    # 한국어 환경에서 통째로 놓친다. 번역되지 않는 `/bin/bash:` 접두사로 찾는다.
    re.compile(r"^/bin/(?:ba)?sh: "),
)

#: 오류처럼 보이지만 정상인 문구. `^no ` 를 넓게 잡으면 여기에 걸려 성공한
#: 실행이 실패로 뒤집힌다.
_NOT_ERRORS = (re.compile(r"^no error in ", re.IGNORECASE),)


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


#: 신호로 죽었을 때 붙이는 설명. 종료 코드 128+N 이 신호 N 을 뜻한다.
_SIGNAL_NAMES = {
    6: "SIGABRT",
    7: "SIGBUS",
    9: "SIGKILL",
    11: "SIGSEGV",
}


#: 로그에 찍히는 격자 크기. 공정이 진행되며 여러 번 나오므로 마지막 것을 쓴다.
_MESH_POINTS_RE = re.compile(r"Points\s*=\s*(\d+)")

#: 영역 하나가 감당하는 점의 대략적 상한.
#:
#: geom.h 의 `struct list_str` 이 개수를 short 로 센다. 영역의 변 목록이
#: 32,767 을 넘으면 카운터가 음수로 뒤집히고, `add_list` 는 그때부터 버퍼를
#: 늘리지 않은 채 계속 쓴다. 삼각형 격자에서 변은 점의 약 3배다.
GRID_POINTS_PER_REGION = 32_767 // 3

#: 이 크기 아래에서 죽었다면 격자 탓으로 보기 어렵다. 엉뚱한 곳을 고치게
#: 만들지 않으려면 짐작하지 않는 편이 낫다.
_GRID_BLAME_FLOOR = 8_000


def mesh_points(log: str) -> int | None:
    """로그가 마지막으로 알린 격자 크기. 없으면 None."""
    found = _MESH_POINTS_RE.findall(log)
    return int(found[-1]) if found else None


def describe_abnormal_exit(exit_code: int, log: str = "") -> str | None:
    """신호로 죽은 실행에 붙일 설명. 정상 종료면 None.

    **세그폴트가 나면 로그가 통째로 빈다** — 버퍼가 플러시되지 못하고 사라지기
    때문이다. 그러면 오류 줄이 하나도 없어 화면에 아무 단서도 남지 않는다.
    입력 문법 문제로 오해하기 딱 좋아서, 무엇이 일어났는지 대신 적어 준다.

    격자가 컸다면 그 숫자를 근거로 원인을 짚는다. 작았다면 짐작하지 않는다 —
    비정상 종료의 원인이 격자 하나뿐인 것은 아니다.
    """
    if exit_code <= 128:
        return None
    name = _SIGNAL_NAMES.get(exit_code - 128)
    if name is None:
        return None

    opening = (
        f"시뮬레이터가 비정상 종료했습니다({name})."
        " 입력 문법 문제가 아니라 시뮬레이터 내부에서 죽은 것입니다."
    )

    points = mesh_points(log)
    if points is not None and points >= _GRID_BLAME_FLOOR:
        return (
            f"{opening} 마지막으로 만든 격자가 {points:,}점입니다."
            f" 영역 하나가 약 {GRID_POINTS_PER_REGION:,}점을 넘으면 시뮬레이터"
            " 내부 한계에 걸립니다 — 촘촘한 구간을 좁히거나 격자선을 줄여 보세요."
            " 한계는 영역별이라, 층이 여러 개면 전체 점수는 더 커도 됩니다."
        )

    return (
        f"{opening} 격자를 성기게 하면 넘어가는 경우가 많습니다"
        " — 촘촘한 구간을 좁히거나 반대 방향 격자선을 줄여 보세요."
    )


def extract_errors(log: str) -> tuple[str, ...]:
    """로그(stdout+stderr)에서 오류 줄만 골라낸다."""
    return tuple(
        stripped
        for line in log.splitlines()
        if (stripped := line.strip())
        and not any(safe.search(stripped) for safe in _NOT_ERRORS)
        and any(pattern.search(stripped) for pattern in _ERROR_PATTERNS)
    )


#: 소스에서 구조 저장 명령을 찾는 패턴.
#:
#: SUPREM 은 커맨드와 파라미터를 고유 접두사로 해석한다. `structure` 의 최단
#: 고유 접두사는 `stru` 다 — `str` 까지는 `stress` 와 겹친다. 파라미터도
#: `out`, `outf`, `outfile` 이 모두 같은 것을 가리킨다. 해석은 대소문자를
#: 구분하므로 소문자만 본다.
_STRUCTURE_OUT_RE = re.compile(
    r"^\s*stru\w*\s+(?:[^\n#]*?\s)?out\w*\s*=\s*(\S+)", re.MULTILINE
)


def collect_structure_files(workdir: Path, source: str = "") -> tuple[Path, ...]:
    """생성된 `.str` 파일을 공정 단계 순서로 모은다.

    순서는 **소스에 적힌 `structure out=` 등장 순서**를 따른다. 그것이 사용자가
    의도한 공정 흐름이기 때문이다.

    파일시스템 타임스탬프로 정렬하면 안 된다. 리눅스는 inode 시각을 타이머 틱
    단위로 캐시된 시계에서 가져오므로, 같은 틱(수 ms) 안에 쓰인 파일들은
    `st_mtime_ns` 까지 완전히 동일한 값을 받는다. 실제로 1초 안에 끝나는
    시뮬레이션에서 두 파일의 mtime_ns 가 정확히 같았고, 안정 정렬이 glob
    순서(대체로 이름순)를 그대로 남겨 공정 순서가 뒤집혔다.

    소스에 언급되지 않은 파일(사용자가 셸로 직접 만든 경우 등)은 뒤에 이름순으로
    붙인다. 버리지 않는 이유는 산출물 유실이 순서 오류보다 나쁘기 때문이다.
    """
    present = {path.name: path for path in workdir.glob("*.str")}

    ordered: list[Path] = []
    for match in _STRUCTURE_OUT_RE.finditer(source):
        name = Path(match.group(1)).name
        path = present.pop(name, None)
        if path is not None:
            ordered.append(path)

    ordered.extend(sorted(present.values(), key=lambda p: p.name))
    return tuple(ordered)
