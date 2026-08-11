"""시뮬레이션 실행.

사용자 소스를 잡별 스크래치 디렉토리에 기록하고 컨테이너 안에서 돌린다.
격리 근거와 실측 검증 내용은 sandbox.py 참조.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.runner.results import (
    SimulationResult,
    collect_structure_files,
    extract_errors,
)
from app.runner.sandbox import (
    SOURCE_FILENAME,
    SandboxLimits,
    build_sandbox_argv,
    build_stdin_script,
    container_name,
)
from app.runner.watchdog import OutputWatchdog
from app.runner.workdir import directory_size, prune_workdir

#: conmon 이 컨테이너를 죽인 뒤 클라이언트가 정리될 여유. 클라이언트 타임아웃이
#: 먼저 터지면 컨테이너가 남을 수 있어 항상 컨테이너 쪽이 먼저 끝나야 한다.
_CLIENT_TIMEOUT_MARGIN_SECONDS = 30

DEFAULT_IMAGE = "tcad/suprem:latest"

#: 로그 상한. 사용자 코드는 무한 출력을 낼 수 있고, 그대로 두면 DB 한 행이
#: 기가바이트가 된다. 앞뒤를 남기는 이유는 오류가 보통 끝에 나오는데 무엇을
#: 하다가 그랬는지는 앞에 있기 때문이다.
_MAX_LOG_CHARS = 200_000
_LOG_HEAD_CHARS = 150_000


def run_simulation(
    source: str,
    workdir: Path,
    image: str = DEFAULT_IMAGE,
    limits: SandboxLimits | None = None,
) -> SimulationResult:
    """`.in` 소스를 샌드박스에서 실행한다.

    Args:
        source: 사용자가 작성한 SUPREM4GS 소스. **셸 스크립트로 취급해야 한다** —
            시뮬레이터가 인식하지 못한 첫 단어를 /bin/bash 로 넘기기 때문이다.
            이 문자열은 파일로만 전달되고 실행 인자에는 절대 들어가지 않는다.
        workdir: 잡 전용 스크래치 디렉토리(절대 경로). 컨테이너가 쓸 수 있는
            유일한 경로이며, 결과 `.str` 도 여기에 떨어진다.
        image: 실행할 컨테이너 이미지.
        limits: 자원 상한.

    Returns:
        SimulationResult. 종료 코드만 보지 말고 `succeeded` 를 볼 것.
    """
    limits = limits or SandboxLimits()
    workdir.mkdir(parents=True, exist_ok=True)
    source = _write_source(workdir, source)

    argv = build_sandbox_argv(image=image, host_workdir=workdir, limits=limits)
    limit_bytes = limits.max_output_mb * 1_048_576

    timed_out = False
    # /work 는 호스트 bind mount 라 컨테이너 옵션으로 크기를 묶을 수 없다
    # (tmpfs 로 만들면 산출물이 컨테이너와 함께 사라진다). 도는 동안 밖에서
    # 지켜보다가 넘으면 컨테이너를 죽인다. 실측으로 확인한 문제다 — 잡 하나가
    # 몇 초 만에 호스트 디스크에 200MB 를 썼고 아무도 막지 않았다.
    watchdog = OutputWatchdog(workdir, limit_bytes, container_name(workdir))

    with watchdog:
        try:
            completed = subprocess.run(  # noqa: S603 - argv 는 사용자 입력에 의존하지 않는다
                argv,
                input=build_stdin_script(),
                stdout=subprocess.PIPE,
                # stderr 를 분리하면 안 된다. 시뮬레이터의 커맨드 오류와, 셸
                # fall-through 로 실행된 명령의 오류가 전부 stderr 로 나간다
                # (`cat: /etc/shadow: Permission denied` 등). 따로 버리면
                # 사용자는 아무 설명 없이 빈 로그만 보게 되고, 오류 탐지도
                # 실패한다.
                stderr=subprocess.STDOUT,
                text=True,
                timeout=limits.timeout_seconds + _CLIENT_TIMEOUT_MARGIN_SECONDS,
                check=False,
            )
            exit_code, log = completed.returncode, completed.stdout
        except subprocess.TimeoutExpired as expired:
            # 컨테이너는 --timeout 으로 conmon 이 이미 죽였어야 한다. 여기까지
            # 왔다면 클라이언트가 늦게 정리된 경우이므로 부분 출력만 살린다.
            timed_out = True
            exit_code = -1
            log = _decode_partial(expired.stdout)

    log = _truncate_log(log)
    errors = list(extract_errors(log))

    # 실행 직후 크기를 잰다. 워치독만으로는 부족하다 — 폴링 주기보다 빨리
    # 끝나는 쓰기를 놓친다. 실제로 400MB `dd` 가 폴링 사이에 끝나서, 상한을
    # 50배 넘겼는데도 잡이 "성공"으로 기록됐다. 정리는 되지만 사용자는 자기
    # 결과가 왜 사라졌는지 알 수 없다.
    final_size = directory_size(workdir)
    if watchdog.tripped or final_size > limit_bytes:
        # 산출물을 신뢰할 수 없다(쓰다 만 파일일 수 있다). 실패로 기록한다.
        errors.append(
            f"출력이 상한({limits.max_output_mb}MB)을 넘었습니다. "
            f"실행을 중단하고 결과를 버렸습니다."
        )

    structure_files = collect_structure_files(workdir, source)

    # 산출물이 아닌 파일은 남길 이유가 없다. 사용자가 만든 임의 파일까지
    # 보관하면 잡이 쌓일수록 디스크가 계속 는다.
    prune_workdir(workdir)

    return SimulationResult(
        exit_code=exit_code,
        log=log,
        timed_out=timed_out,
        structure_files=structure_files,
        errors=tuple(errors),
    )


def normalise_source(source: str) -> str:
    """시뮬레이터에 넘길 수 있는 형태로 다듬는다.

    **마지막 줄에 개행이 없으면 그 줄이 실행되지 않는다.** 실측으로 확인했다 —
    CMOS 예제를 끝 개행 없이 돌리면 마지막 `structure out=` 이 빠져 산출물이
    14개만 나오고, 이어서 러너가 보내는 `quit` 이 미완성 줄에 붙어
    "illegal input" 이 난다. 개행을 넣으면 15개가 나오고 오류도 없다.

    브라우저 편집기에서 마지막 줄 끝에 Enter 를 치지 않는 것은 아주 흔하다.
    사용자 탓으로 둘 수 없다.

    줄바꿈도 LF 로 맞춘다. 레포의 예제 파일들이 CRLF 라 붙여 넣으면 그대로
    들어온다.
    """
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def _write_source(workdir: Path, source: str) -> str:
    """job.in 을 쓰고, 실제로 실행될 내용을 돌려준다.

    돌려준 값은 산출물 순서를 정하는 데도 쓰이므로 파일과 같아야 한다.
    """
    text = normalise_source(source)
    (workdir / SOURCE_FILENAME).write_text(text)
    return text


def _truncate_log(log: str) -> str:
    """로그를 상한 안으로 줄인다.

    사용자 코드는 무한 출력을 낼 수 있다. 그대로 저장하면 DB 한 행이
    기가바이트가 되고, 화면도 그걸 그대로 받는다. 앞뒤를 남기는 이유는 오류가
    보통 끝에 나오는데 무엇을 하다 그랬는지는 앞에 있기 때문이다.
    """
    if len(log) <= _MAX_LOG_CHARS:
        return log

    tail_chars = _MAX_LOG_CHARS - _LOG_HEAD_CHARS
    omitted = len(log) - _MAX_LOG_CHARS
    return (
        f"{log[:_LOG_HEAD_CHARS]}\n"
        f"…… 중간 {omitted:,}자 생략 (로그가 상한을 넘었습니다) ……\n"
        f"{log[-tail_chars:]}"
    )


def _decode_partial(captured: bytes | str | None) -> str:
    if captured is None:
        return ""
    if isinstance(captured, bytes):
        return captured.decode("utf-8", errors="replace")
    return captured
