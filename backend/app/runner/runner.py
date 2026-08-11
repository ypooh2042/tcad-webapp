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
)

#: conmon 이 컨테이너를 죽인 뒤 클라이언트가 정리될 여유. 클라이언트 타임아웃이
#: 먼저 터지면 컨테이너가 남을 수 있어 항상 컨테이너 쪽이 먼저 끝나야 한다.
_CLIENT_TIMEOUT_MARGIN_SECONDS = 30

DEFAULT_IMAGE = "tcad/suprem:latest"


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
    (workdir / SOURCE_FILENAME).write_text(source)

    argv = build_sandbox_argv(image=image, host_workdir=workdir, limits=limits)

    timed_out = False
    try:
        completed = subprocess.run(  # noqa: S603 - argv 는 사용자 입력에 의존하지 않는다
            argv,
            input=build_stdin_script(),
            stdout=subprocess.PIPE,
            # stderr 를 분리하면 안 된다. 시뮬레이터의 커맨드 오류와, 셸
            # fall-through 로 실행된 명령의 오류가 전부 stderr 로 나간다
            # (`cat: /etc/shadow: Permission denied` 등). 따로 버리면 사용자는
            # 아무 설명 없이 빈 로그만 보게 되고, 오류 탐지도 실패한다.
            stderr=subprocess.STDOUT,
            text=True,
            timeout=limits.timeout_seconds + _CLIENT_TIMEOUT_MARGIN_SECONDS,
            check=False,
        )
        exit_code, log = completed.returncode, completed.stdout
    except subprocess.TimeoutExpired as expired:
        # 컨테이너는 --timeout 으로 conmon 이 이미 죽였어야 한다. 여기까지 왔다면
        # 클라이언트가 늦게 정리된 경우이므로 부분 출력만 살려서 돌려준다.
        timed_out = True
        exit_code = -1
        log = _decode_partial(expired.stdout)

    return SimulationResult(
        exit_code=exit_code,
        log=log,
        timed_out=timed_out,
        structure_files=collect_structure_files(workdir, source),
        errors=extract_errors(log),
    )


def _decode_partial(captured: bytes | str | None) -> str:
    if captured is None:
        return ""
    if isinstance(captured, bytes):
        return captured.decode("utf-8", errors="replace")
    return captured
