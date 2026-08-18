"""출력 크기 감시.

/work 는 호스트 bind mount 라 컨테이너 옵션으로 크기를 묶을 수 없다(tmpfs 로
만들면 산출물이 컨테이너와 함께 사라진다). 그래서 도는 동안 밖에서 지켜본다.

죽일 때 `podman kill` 을 쓴다. 클라이언트 프로세스만 죽이면 컨테이너가 살아남아
계속 디스크를 쓴다.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.runner.control import kill_container
from app.runner.workdir import directory_size

logger = logging.getLogger(__name__)

#: 크기를 확인하는 주기.
#:
#: 이 값이 곧 "얼마나 넘길 수 있는가"를 정한다 — 주기 사이에 쓴 만큼은 막지
#: 못한다. 반대로 너무 잦으면 파일이 많은 디렉토리에서 rglob 비용이 붙는다.
#:
#: 폴링만으로는 원천 차단이 안 된다는 점이 중요하다. 실제로 400MB `dd` 는
#: 주기보다 빨리 끝나 워치독을 통째로 빠져나갔다. 그래서 러너가 실행 직후
#: 크기를 한 번 더 재고, 이 워치독은 "오래 쓰는 잡의 최대 사용량"을 묶는
#: 역할만 맡는다. 완전한 차단은 파일시스템 쿼터로만 가능하다.
_POLL_SECONDS = 1.0


class OutputWatchdog:
    """작업 디렉토리가 상한을 넘으면 컨테이너를 죽인다."""

    def __init__(
        self, workdir: Path, limit_bytes: int, container: str
    ) -> None:
        self.workdir = workdir
        self.limit_bytes = limit_bytes
        self.container = container
        self.tripped = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)

    def __enter__(self) -> OutputWatchdog:
        self._thread.start()
        return self

    def __exit__(self, *_exception) -> None:
        self._stop.set()
        self._thread.join(timeout=_POLL_SECONDS * 2)

    def _watch(self) -> None:
        while not self._stop.wait(_POLL_SECONDS):
            try:
                size = directory_size(self.workdir)
            except OSError:
                continue  # 디렉토리가 정리되는 중이면 그만 봐도 된다

            if size <= self.limit_bytes:
                continue

            self.tripped = True
            logger.warning(
                "출력 상한 초과로 컨테이너를 종료합니다: %s (%d bytes)",
                self.container,
                size,
            )
            self._kill()
            return

    def _kill(self) -> None:
        # 죽이지 못해도 감시 자체는 끝난다. 뒤이어 실행 후 검사가 잡는다.
        kill_container(self.container)
