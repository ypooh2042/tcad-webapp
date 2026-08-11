"""샌드박스 실행 인자 구성.

SUPREM4GS 인터프리터는 인식하지 못한 첫 단어를 /bin/bash 로 넘긴다. 사용자가
제출하는 .in 파일은 시뮬레이션 스크립트인 동시에 임의 셸 스크립트다. 실측으로
확인했다(.in 에 `id` 한 줄 → 호스트 유저의 uid/gid/그룹이 그대로 출력됨).

그래서 이 모듈의 규칙은 하나다: **사용자 입력은 실행 인자에 절대 들어가지 않는다.**
소스는 스크래치 디렉토리 안 고정 파일명으로 기록되고, 컨테이너에는 그 고정
이름만 전달된다.

런타임은 Podman 루트리스를 쓴다. 데몬이 없고 컨테이너가 user namespace 를 통해
비특권 유저로 돌기 때문에, 탈출당해도 공격자가 얻는 것이 host root 가 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: 컨테이너 안에서 스크래치 디렉토리가 마운트되는 위치. 쓰기가 허용되는 유일한 경로.
SANDBOX_WORKDIR = "/work"

#: 사용자 소스가 기록되는 고정 파일명. 사용자가 이름을 정하지 못하게 한다.
SOURCE_FILENAME = "job.in"

#: 컨테이너 안 실행 유저 (Containerfile 의 suprem 유저와 일치해야 함).
SANDBOX_UID = "10001"
SANDBOX_GID = "10001"


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    """자원 상한.

    기본값은 6코어 홈서버에서 동시 4잡을 돌리는 것을 전제로 한다. 이 서버는
    code-server 등 다른 서비스도 함께 돌리므로 한 잡이 CPU 를 독점하면 안 된다.
    """

    cpus: float = 1.0
    memory_mb: int = 2048
    max_pids: int = 128
    timeout_seconds: int = 600


def build_sandbox_argv(
    image: str,
    host_workdir: Path,
    limits: SandboxLimits,
) -> tuple[str, ...]:
    """컨테이너 실행 인자를 만든다.

    반환값은 사용자 입력에 전혀 의존하지 않는다. 같은 이미지·디렉토리·상한이면
    항상 같은 인자가 나온다.

    Raises:
        ValueError: host_workdir 가 절대 경로가 아닐 때. 상대 경로는 실행 시점의
            cwd 에 따라 의도치 않은 호스트 경로를 마운트할 수 있다.
    """
    if not host_workdir.is_absolute():
        raise ValueError(
            f"스크래치 디렉토리는 절대 경로여야 합니다: {host_workdir}"
        )

    return (
        "podman",
        "run",
        "--rm",
        # stdin 을 붙이지 않으면 `source job.in` 이 시뮬레이터에 전달되지 않아
        # 배너만 찍고 조용히 종료된다(exit 0). --tty 는 붙이지 않는다. 출력에
        # 제어문자가 섞여 로그 파싱이 깨진다.
        "--interactive",
        # ── 격리 ──────────────────────────────────────────────
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--read-only",
        # 루트리스 Podman 은 기본적으로 호스트 유저를 컨테이너 uid 0 에 매핑하고
        # 나머지 uid 는 서브uid(10만번대)로 보낸다. 그 상태로 --user 10001 을 쓰면
        # 컨테이너가 스크래치 디렉토리를 읽지도 쓰지도 못한다(실측 확인).
        # keep-id 로 호스트 유저를 컨테이너의 10001 에 직접 매핑하면,
        # 컨테이너 안에서는 전용 비특권 uid 로 보이고 호스트에는 워커 소유로
        # 파일이 떨어져 결과를 그대로 읽을 수 있다.
        "--userns", f"keep-id:uid={SANDBOX_UID},gid={SANDBOX_GID}",
        "--user", f"{SANDBOX_UID}:{SANDBOX_GID}",
        # 시뮬레이터가 임시 파일을 쓸 수 있어야 하지만 호스트에 남으면 안 된다.
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        # ── 자원 상한 ─────────────────────────────────────────
        "--cpus", str(limits.cpus),
        "--memory", f"{limits.memory_mb}m",
        "--pids-limit", str(limits.max_pids),
        # conmon 이 직접 컨테이너를 죽인다. 클라이언트 프로세스만 타임아웃시키면
        # 컨테이너가 계속 살아남아 CPU 를 물고 있을 수 있다.
        "--timeout", str(limits.timeout_seconds),
        # ── 작업 공간 ─────────────────────────────────────────
        "--volume", f"{host_workdir}:{SANDBOX_WORKDIR}:rw",
        "--workdir", SANDBOX_WORKDIR,
        image,
    )


def build_stdin_script() -> str:
    """시뮬레이터에 넣을 표준입력 스크립트.

    고정 문자열이다. 사용자 소스는 이 스크립트가 아니라 job.in 파일로 전달된다.
    """
    return f"source {SOURCE_FILENAME}\nquit\n"
