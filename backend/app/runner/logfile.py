"""실행 로그 전문을 잡 작업디렉토리에 보관한다.

DB 에 넣는 로그에는 상한이 있다 — 시뮬레이터가 인식하지 못한 첫 단어를
`/bin/bash` 로 넘기므로 사용자는 무한 출력을 낼 수 있고, 한 행이 기가바이트가
되면 목록 조회 하나까지 같이 느려진다. 그래서 상한은 유지하되 **잘린 부분이
사라지지는 않게** 전문을 파일로 남긴다.

산출물(`.str`)과 같은 자리에 두므로 수명도 같다. 세션이 만료돼 청소가 돌면
작업디렉토리째 지워지고, 그때는 DB 에 남은 미리보기만 남는다. 로그만 따로
오래 보관하면 청소가 회수하려던 디스크를 도로 잡아먹는다.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: 작업디렉토리 안의 전문 로그 파일 이름.
FULL_LOG_NAME = "run.log"


def full_log_path(workdir: Path) -> Path:
    return Path(workdir) / FULL_LOG_NAME


def write_full_log(workdir: Path, log: str) -> Path | None:
    """전문을 남긴다.

    **`prune_workdir` 뒤에 불러야 한다.** 그쪽은 `.str` 이 아닌 파일을 전부
    지우므로 먼저 쓰면 방금 쓴 로그가 지워진다.

    Returns:
        쓴 경로. 쓰지 못했으면 None.
    """
    path = full_log_path(workdir)
    try:
        path.write_text(log, encoding="utf-8")
    except OSError:
        # 로그를 못 남긴다고 잡을 실패시킬 이유는 없다. 결과와 미리보기는
        # 이미 확보돼 있다.
        logger.warning("전문 로그를 남기지 못했습니다: %s", path, exc_info=True)
        return None
    return path


def read_full_log(workdir: Path) -> str | None:
    """전문을 읽는다. 없으면 None — 청소된 잡은 정상적으로 이 경우다."""
    try:
        return full_log_path(workdir).read_text(encoding="utf-8")
    except OSError:
        return None
