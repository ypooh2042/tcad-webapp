"""실행 중인 컨테이너를 밖에서 멈추는 길.

컨테이너 이름은 workdir 에서 결정론적으로 나오므로(`tcad-job-<uuid>`),
워커와 따로 도는 프로세스도 DB 의 workdir 만 있으면 죽일 수 있다. 워커에게
신호를 전달할 통로를 따로 만들지 않아도 된다.

`podman kill` 을 쓴다. 클라이언트 프로세스만 죽이면 컨테이너가 살아남아 계속
CPU 와 디스크를 쓴다.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

#: 죽이기를 기다리는 시간. 여기서 막히면 요청 처리 전체가 붙잡힌다.
_KILL_TIMEOUT_SECONDS = 30


def kill_container(name: str) -> bool:
    """컨테이너를 죽인다. 성공 여부를 돌려준다.

    실패해도 예외를 올리지 않는다. 이미 끝났을 수도 있고, 그 경우 죽일 것이
    없는 것이 정상이다. 호출부는 대개 실패해도 할 일을 계속해야 한다.
    """
    try:
        result = subprocess.run(  # noqa: S603 - 이름은 서버가 정한 값이다
            ("podman", "kill", name),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_KILL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        logger.exception("컨테이너 종료 실패: %s", name)
        return False
    return result.returncode == 0
