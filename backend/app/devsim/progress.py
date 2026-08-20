"""돌고 있는 소자 해석의 진행률.

SUPREM 잡은 `.str` 파일 개수를 세지만(`app/jobs/progress.py`), 소자 해석에는
`structure out=` 이 없다. 대신 해석기가 바이어스 점마다 `iv.jsonl` 에 한 줄씩
흘려보내므로 그 줄을 센다 — 로그를 못 쓰는 사정은 같다(stdout 은 파이프로 받아
끝날 때 한꺼번에 저장한다).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.jobs.progress import Progress

STREAM_FILENAME = "iv.jsonl"


def _describe(row: dict) -> str:
    """마지막으로 푼 점을 사람이 읽을 문구로. 예: `Vg=1V, 1.5V`."""
    parts = [f"{name}={value:g}V" for name, value in sorted(row.get("steps", {}).items())]
    sweep = row.get("sweep")
    if sweep is not None:
        parts.append(f"{sweep:g}V")
    return ", ".join(parts)


def scan_devsim_progress(workdir: Path, total: int) -> Progress | None:
    """푼 바이어스 점 수. 셀 수 없으면 `None`.

    `0/0` 을 돌려주지 않는다. 화면이 "0단계 중 0단계"라고 거짓말을 하게 된다.
    """
    if total <= 0:
        return None

    workdir = Path(workdir)
    if not workdir.is_dir():
        # 작업디렉토리가 사라졌다면 진행 상황을 **모르는** 것이다. 0 으로
        # 보여주면 아직 시작 안 한 잡과 구분이 안 된다.
        return None

    try:
        text = (workdir / STREAM_FILENAME).read_text()
    except OSError:
        # 아직 한 점도 못 풀었다. 그건 0/total 이 맞다.
        return Progress(done=0, total=total, latest=None)

    done = 0
    latest: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            # 해석기가 줄을 쓰는 도중에 읽었다. 다음 폴링에서 온전해진다.
            continue
        done += 1
        latest = _describe(row)
    return Progress(done=done, total=total, latest=latest)
