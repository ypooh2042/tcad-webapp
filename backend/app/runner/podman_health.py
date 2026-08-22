"""podman 자체가 뜨지 못하는 상태를 알아보고 되살린다.

루트리스 podman 은 **pause 프로세스**(`catatonit -P`) 하나를 띄워 user
namespace 를 붙들어 두고, 뒤따르는 모든 명령이 그 네임스페이스로 들어간다.
그 프로세스의 pid 는 `$XDG_RUNTIME_DIR/libpod/tmp/pause.pid` 에 있다.

이 짜임이 어긋나면 podman 은 시뮬레이션을 시작조차 못 하고 이렇게 죽는다::

    running `/usr/bin/newuidmap <pid> 0 1000 1 1 100000 65536`:
        newuidmap: write to uid_map failed: Operation not permitted
    invalid internal status, try resetting the pause process with
        "podman system migrate"

`newuidmap` 은 setuid 루트지만, **이미 user namespace 안**에서 부르면 그
안의 uid 0 일 뿐이라 바깥에 대해 아무 권한이 없다. podman 이 낡은 pause
네임스페이스로 들어간 뒤 거기서 새 매핑을 쓰려 하면 정확히 이 오류가 난다.

**podman 이 권하는 `podman system migrate` 를 그대로 따르면 안 된다.**
그 명령은 도는 컨테이너를 전부 멈춘다. 이 서버의 postgres 와 redis 는
systemd 가 관리하지 않아 스스로 돌아오지 않고, 앱이 통째로 죽는다.

대신 최소한만 한다: `pause.pid` 를 치운다. 그러면 다음 podman 이 pause
프로세스를 새로 만든다. 살아 있는 프로세스는 죽이지 않는다 — 밖에서는 그것이
정말 고장인지 알 수 없고, 남겨 둬도 무해하다(실측: 중복 pause 프로세스 일곱
개가 같은 네임스페이스를 정상 매핑으로 붙들고 있었고 컨테이너는 모두
정상이었다. 그중 일부를 죽여도 도는 컨테이너는 멀쩡했다).

딱 하나 확실히 판정할 수 있는 고장은 **매핑이 비어 있는 user namespace 를
붙들고 있는 pause 프로세스**다. 그 안에서는 누구도 권한이 없으므로 위 오류가
필연이다. 그것만 죽인다.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

#: pause 프로세스를 새로 만들어 주는 systemd 사용자 유닛.
#:
#: 워커 유닛은 `NoNewPrivileges=true` 로 돈다. **그러면 setuid 인 `newuidmap`
#: 이 무효가 되어, 워커 안에서는 새 user namespace 를 만들 수 없다** (실측:
#: 같은 podman 명령이 NNP 를 켜면 `write to uid_map failed: Operation not
#: permitted`, 끄면 성공). 지금까지 돌아간 것은 살아 있는 pause 프로세스에
#: 합류만 했기 때문이다.
#:
#: 그래서 pause.pid 를 치우고 그 자리에서 다시 돌려 봐야 같은 곳에서 막힌다.
#: 만드는 일은 NNP 를 물려받지 않는 별도 유닛에 맡기고, 워커는 거기서 생긴
#: 네임스페이스에 합류한다.
PAUSE_UNIT = "tcad-podman.service"

#: systemd 에 부탁하고 기다리는 한도. 이미지 풀 같은 것이 아니라 프로세스
#: 하나를 띄우는 일이라 길 이유가 없다. 여기서 막히면 잡 슬롯이 묶인다.
_PAUSE_UNIT_TIMEOUT_SECONDS = 60.0

#: 이 문구들이 보이면 podman 기반 자체가 못 뜬 것이다. 시뮬레이터가 낸 오류와
#: 구별해야 한다 — 시뮬레이터 실패는 다시 돌려도 같은 결과다.
_INFRA_MARKERS = (
    "newuidmap",
    "newgidmap",
    "pause process",
    "podman system migrate",
    "cannot join namespace",
    "cannot join mount namespace",
    "invalid internal status",
)

#: podman 이 기반 문제로 죽었을 때 쓰는 종료코드. 컨테이너가 시작조차 못 한
#: 경우이므로, 다시 시도해도 사용자 코드가 두 번 도는 일은 없다.
_PODMAN_ERROR_EXIT = 125

#: 사용자에게 보이는 안내. 로그에 podman 원문만 남으면 자기 입력을 의심한다.
ADVICE = (
    "컨테이너 실행 기반(podman)이 일시적으로 뜨지 못했습니다. "
    "시뮬레이션 코드 문제가 아닙니다. "
    "계속되면 deploy/repair-podman.sh 를 실행하세요 — "
    "podman 이 안내하는 `podman system migrate` 는 도는 컨테이너를 "
    "전부 멈추므로 이 서버에서는 쓰면 안 됩니다."
)


def mentions_infra_failure(log: str | None) -> bool:
    """로그 문구만으로 판정한다. 종료코드가 없는 자리에서 쓴다.

    재메시가 그런 자리다 — gmsh 산출물이 없으면 podman 원문을 담은
    `RuntimeError` 를 낼 뿐 종료코드를 돌려주지 않는다. 문구가 꽤 구체적이라
    (`newuidmap`, `pause process`, …) 이것만으로도 시뮬레이터 자신의 실패와
    헷갈리지 않는다.
    """
    if not log:
        return False
    lowered = log.lower()
    return any(marker in lowered for marker in _INFRA_MARKERS)


def looks_like_infra_failure(exit_code: int, log: str | None) -> bool:
    """podman 기반이 못 떠서 실패한 것인가.

    성공한 실행은 절대 여기 걸리지 않는다. 종료코드가 podman 자신의 오류값일
    때만, 그리고 알려진 문구가 있을 때만 참이다. 문구를 요구하는 이유는 125 가
    "이미지가 없다" 같은 되살릴 수 없는 실패에도 쓰이기 때문이다.
    """
    if exit_code != _PODMAN_ERROR_EXIT:
        return False
    return mentions_infra_failure(log)


def pause_pid_path() -> Path:
    """pause 프로세스의 pid 파일 위치.

    `XDG_RUNTIME_DIR` 은 로그인 셸이 아닌 곳에서 비어 있다(편집기 터미널,
    cron, 원격 실행). podman 자신과 같은 방식으로 되짚는다.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(runtime) / "libpod" / "tmp" / "pause.pid"


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _is_alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def _has_no_uid_mapping(pid: int) -> bool:
    """이 프로세스의 user namespace 에 매핑이 비어 있는가."""
    try:
        return Path(f"/proc/{pid}/uid_map").read_text().strip() == ""
    except OSError:
        return False


def _is_ours(pid: int) -> bool:
    """이 프로세스가 우리 유저 소유인가. 남의 것을 죽이지 않기 위한 확인이다."""
    try:
        return Path(f"/proc/{pid}").stat().st_uid == os.getuid()
    except OSError:
        return False


def ensure_pause_process(timeout: float = _PAUSE_UNIT_TIMEOUT_SECONDS) -> str | None:
    """pause 프로세스를 NNP 바깥에서 만들어 달라고 systemd 에 부탁한다.

    무엇을 했는지 돌려주고, 부탁이 닿지 않으면 None. **실패해도 예외를 내지
    않는다** — 되살리기는 최선의 시도이지 보장이 아니고, 여기서 터지면 원래의
    실패 원문까지 묻힌다. systemd 사용자 관리자가 없는 개발 상자에서도 조용히
    넘어간다.
    """
    try:
        done = subprocess.run(
            ["systemctl", "--user", "start", PAUSE_UNIT],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        logger.exception("%s 를 시작하지 못했습니다", PAUSE_UNIT)
        return None

    if done.returncode != 0:
        logger.warning("%s 시작 실패: %s", PAUSE_UNIT, done.stderr.strip())
        return None
    return f"{PAUSE_UNIT} 로 pause 프로세스를 새로 만들었습니다"


def repair(pause_pid: Path | None = None) -> str | None:
    """되살리기를 시도한다. 무엇을 했는지 돌려주고, 할 것이 없으면 None.

    되살리기가 성공했는지는 여기서 판정하지 않는다 — 판정은 다시 실행해 보는
    것뿐이고, 그것은 호출부의 몫이다.
    """
    path = pause_pid if pause_pid is not None else pause_pid_path()
    if not path.exists():
        return None  # podman 이 알아서 새로 만든다

    pid = _read_pid(path)

    if pid is None or not _is_alive(pid):
        _unlink(path)
        return f"없는 프로세스를 가리키던 pause.pid 를 치웠습니다 ({path})"

    # 매핑이 비어 있는 네임스페이스는 확실한 고장이다. pid 가 재사용됐을 수
    # 있으므로 우리 유저 소유인지 한 번 더 확인하고 죽인다.
    if _has_no_uid_mapping(pid) and _is_ours(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            logger.exception("pause 프로세스를 죽이지 못했습니다: %d", pid)
        _unlink(path)
        return f"매핑이 없는 네임스페이스를 붙들던 pause 프로세스({pid})를 정리했습니다"

    _unlink(path)
    return f"pause.pid 를 치워 다음 실행이 새로 만들도록 했습니다 (기존 {pid} 는 그대로 둡니다)"


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        logger.exception("pause.pid 를 지우지 못했습니다: %s", path)


def main() -> int:
    """`python -m app.runner.podman_health` 로 손으로 부를 때.

    ADVICE 는 여기서 찍지 않는다 — 그 문구는 잡 로그를 보는 사용자에게
    "이 스크립트를 돌려 보라"고 말하는 것이라, 스크립트 안에서는 앞뒤가 맞지
    않는다.
    """
    note = repair()
    print(note if note else "손댈 것이 없습니다 — pause.pid 가 없습니다.")
    return 0


if __name__ == "__main__":  # pragma: no cover - 손으로 부르는 진입점
    raise SystemExit(main())
