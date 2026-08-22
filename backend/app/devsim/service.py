"""DevSim 잡 하나를 처음부터 끝까지 돌린다.

`app/runner/runner.py:run_simulation` 과 같은 자리에 있는 함수다. 워커가 잡의
`kind` 를 보고 둘 중 하나를 부른다.

**재메시는 선택이 아니라 필수다.** 실측으로 확인했다: `nmos.in` 최종 구조는
실리콘 변 2467 개 중 575 개(23%)의 EdgeCouple 이 정확히 0 이다(둔각 삼각형).
결합이 0 인 노드는 연속방정식이 특이해져 뉴턴이 선다 — 수렴 기준을 고쳐도
15 점 중 1 점에서 멈췄고, 재메시하면 15/15 다. 그래서 여기서 항상 다시 짠다.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.devsim.payload import build_payload
from app.devsim.resolve import ElectrodeNotFound
from app.devsim.spec import DeviceSpec
from app.remesh.service import DEFAULT_IMAGE as REMESH_IMAGE
from app.remesh.service import remesh
from app.runner.logfile import write_full_log
from app.runner.podman_health import ADVICE, looks_like_infra_failure
from app.runner.sandbox import SandboxLimits, build_sandbox_argv, container_name
from app.runner.watchdog import OutputWatchdog
from app.runner.workdir import DEVSIM_ARTIFACTS, prune_workdir
from app.str_parser.errors import StructureFormatError
from app.str_parser.parser import parse_structure

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "tcad/devsim:latest"

#: 잡 작업디렉토리 안의 고정 파일 이름. 사용자가 이름을 정하지 못한다.
STRUCTURE_FILENAME = "structure.str"
REMESHED_FILENAME = "remeshed.str"
DEVICE_FILENAME = "device.json"
RESULT_FILENAME = "iv.json"
STREAM_FILENAME = "iv.jsonl"

#: 컨테이너가 죽었을 때 클라이언트 쪽이 먼저 포기하지 않도록 두는 여유.
_CLIENT_TIMEOUT_MARGIN_SECONDS = 30

#: 소자 해석 기본 상한.
#:
#: 시간은 **큰 구조**를 기준으로 잡는다. 실측 두 가지:
#:
#:     nmos.in  재메시 후  8,143 노드 — 바이어스 점당 약 1.6 초
#:     cmos.in  재메시 후 50,062 노드 — 바이어스 점당 약  20 초
#:
#: 직접 솔버라 노드 수에 초선형으로 는다(6.1 배 노드에 12.5 배 시간).
#: 예전 900 초는 nmos 기준이었고, 큰 구조에서는 45 점밖에 못 돌려
#: 42 점짜리 인버터 부하선이 실제로 중간에 잘렸다. `spec.MAX_TOTAL_POINTS`(300)
#: 을 다 쓴 해석이 큰 구조에서 끝나도록 6000 초로 잡는다.
#:
#: 길게 잡아도 잡 슬롯이 묶이는 것이 걱정되지 않는 이유: 사용자가 중단할 수
#: 있고(`routes_jobs.cancel`), 중간까지의 곡선은 `iv.jsonl` 에 남아 건진다.
#:
#: 직접 솔버가 메모리를 쓰므로 suprem 기본값(2 GB)보다 넉넉히 준다.
DEFAULT_LIMITS = SandboxLimits(
    cpus=1.0, memory_mb=4096, max_pids=128, timeout_seconds=6000, max_output_mb=256
)


@dataclass(frozen=True, slots=True)
class DeviceResult:
    exit_code: int
    log: str
    timed_out: bool
    errors: tuple[str, ...]
    #: 풀린 결과. 도중에 끊겨도 거기까지는 담긴다.
    dataset: dict[str, Any] | None
    #: 산출물로 남길 파일들.
    artifacts: tuple[Path, ...]
    #: 제출된 해석 조건 원문. 결과를 표에 남길 때 함께 보관한다.
    spec_json: str = ""

    @property
    def succeeded(self) -> bool:
        """한 점이라도 풀렸으면 성공이다.

        수렴에 실패한 점은 건너뛰고 이어 간다. 스윕 끝쪽 몇 점이 발산하는 것은
        흔한 일이고 그 앞의 곡선은 멀쩡하므로, 그것까지 실패로 적으면 쓸 수 있는
        결과를 버리게 된다. 어느 점이 빠졌는지는 `dataset["failures"]` 에 남는다.
        """
        return (
            not self.timed_out
            and not self.errors
            and self.exit_code == 0
            and bool(self.dataset)
            and self.dataset.get("completed", 0) > 0
        )


def _prepare_device(workdir: Path, spec: DeviceSpec) -> int:
    """`.str` 을 다시 메시하고 장치 설명을 쓴다. 바이어스 점 총수를 돌려준다."""
    source = (workdir / STRUCTURE_FILENAME).read_text()
    # **잡 작업디렉토리에서 돌린다.** 컨테이너 이름이 거기서 나오므로, 이렇게
    # 해야 재메시가 도는 동안에도 중단 버튼이 그 컨테이너를 죽일 수 있다.
    rebuilt = remesh(source, image=REMESH_IMAGE, workdir=workdir)
    (workdir / REMESHED_FILENAME).write_text(rebuilt.text)
    logger.info(
        "재메시: 점 %d → %d, 요소 %d → %d",
        rebuilt.old_points,
        rebuilt.new_points,
        rebuilt.old_elements,
        rebuilt.new_elements,
    )

    structure = parse_structure(rebuilt.text)
    payload = build_payload(structure, spec)
    (workdir / DEVICE_FILENAME).write_text(json.dumps(payload))
    return int(payload["plan"]["total"])


def _read_dataset(workdir: Path, total: int) -> dict[str, Any] | None:
    """결과를 읽는다. `iv.json` 이 없으면 흘려보낸 줄에서 되살린다.

    컨테이너가 상한이나 타임아웃으로 죽으면 `iv.json` 을 못 쓴다. 그래도
    거기까지 푼 점들은 `iv.jsonl` 에 남아 있으므로 부분 곡선은 건진다 —
    긴 스윕에서 이게 있고 없고가 크다.
    """
    final = workdir / RESULT_FILENAME
    if final.exists():
        try:
            return json.loads(final.read_text())
        except (OSError, ValueError):
            logger.warning("결과 파일을 읽지 못했습니다", exc_info=True)

    stream = workdir / STREAM_FILENAME
    if not stream.exists():
        return None
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    try:
        for line in stream.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            # 곡선 사이를 옮기는 표시는 점이 아니다. 곡선에도 실패에도 넣지 않는다.
            if entry.get("phase") == "moving":
                continue
            # 흘려보낸 줄에는 푼 점과 건너뛴 점이 섞여 있다. 섞인 채로 곡선에
            # 넣으면 전류가 없는 점에서 그래프가 0 으로 뚝 떨어진다.
            if entry.get("ok") is False or "currents" not in entry:
                failures.append(entry)
            else:
                rows.append(entry)
    except (OSError, ValueError):
        logger.warning("중간 결과를 읽지 못했습니다", exc_info=True)
    if not rows and not failures:
        return None
    return {
        "sweep": None,
        "biases": sorted(rows[0].get("currents", {})) if rows else [],
        "current_unit": "uA/um",
        "rows": rows,
        "failures": failures,
        "total": total,
        "completed": len(rows),
        "error": "해석이 끝나기 전에 멈췄습니다. 여기까지의 결과만 남았습니다.",
    }


def _execute(workdir: Path, image: str, limits: SandboxLimits) -> tuple[int, str, bool]:
    argv = build_sandbox_argv(image=image, host_workdir=workdir, limits=limits)
    # 컨테이너 이름은 workdir 이름에서 결정론적으로 나온다. 중단 버튼이 워커와
    # 신호를 주고받지 않고도 죽일 수 있는 것이 이 규칙 덕이다.
    watchdog = OutputWatchdog(
        workdir, limits.max_output_mb * 1_048_576, container_name(workdir)
    )
    with watchdog:
        try:
            completed = subprocess.run(  # noqa: S603 - argv 는 서버가 만든다
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=limits.timeout_seconds + _CLIENT_TIMEOUT_MARGIN_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as expired:
            partial = expired.output or ""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            return -1, partial, True
    return completed.returncode, completed.stdout, watchdog.tripped


def run_device_simulation(
    source: str,
    workdir: Path,
    image: str = DEFAULT_IMAGE,
    limits: SandboxLimits | None = None,
) -> DeviceResult:
    """스펙(JSON 문자열)을 받아 소자 해석을 돌린다.

    `workdir/structure.str` 은 제출 시점에 API 가 미리 넣어 둔다 — 원본 잡의
    산출물이 나중에 청소돼도 해석 입력이 살아 있어야 하기 때문이다.
    """
    limits = limits or DEFAULT_LIMITS
    workdir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    try:
        spec = DeviceSpec.model_validate_json(source)
    except ValueError as error:
        return DeviceResult(
            exit_code=1,
            log="",
            timed_out=False,
            errors=(f"해석 조건을 읽지 못했습니다: {error}",),
            dataset=None,
            artifacts=(),
            spec_json=source,
        )

    if not (workdir / STRUCTURE_FILENAME).exists():
        return DeviceResult(
            exit_code=1,
            log="",
            timed_out=False,
            errors=("해석할 구조 파일이 없습니다.",),
            dataset=None,
            artifacts=(),
            spec_json=source,
        )

    try:
        total = _prepare_device(workdir, spec)
    except (ElectrodeNotFound, StructureFormatError, ValueError) as error:
        return DeviceResult(
            exit_code=1,
            log="",
            timed_out=False,
            errors=(str(error),),
            dataset=None,
            artifacts=(),
            spec_json=source,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("장치 준비 실패", exc_info=True)
        return DeviceResult(
            exit_code=1,
            log="",
            timed_out=False,
            errors=(f"구조를 소자 모형으로 옮기지 못했습니다: {error}",),
            dataset=None,
            artifacts=(),
            spec_json=source,
        )

    exit_code, log, tripped = _execute(workdir, image, limits)
    timed_out = exit_code == -1

    if looks_like_infra_failure(exit_code, log):
        errors.append(ADVICE)
    if tripped:
        errors.append("산출물이 상한을 넘어 실행을 중단했습니다.")
    if timed_out:
        errors.append("제한 시간을 넘겨 중단했습니다. 스윕 점을 줄여 보세요.")

    dataset = _read_dataset(workdir, total)
    if dataset is None:
        errors.append("해석 결과가 나오지 않았습니다.")
    elif dataset.get("error") and dataset.get("completed"):
        # 부분 결과는 실패가 아니다. 사용자가 볼 곡선이 남아 있다.
        logger.info("해석이 도중에 멈췄습니다: %s", dataset["error"])
    elif dataset.get("error"):
        errors.append(str(dataset["error"]))

    _write_result(workdir, dataset)

    # 입력을 치운다. `device.json` 은 메시 전체가 든 수 MB 짜리이고 `remeshed.str`
    # 은 그보다 크다. 둘 다 결과에서 다시 만들 수 있고, 남겨 두면 쿼터를 잡아먹어
    # 다른 잡의 산출물이 먼저 지워진다.
    prune_workdir(workdir, keep=frozenset(), keep_names=DEVSIM_ARTIFACTS)
    # 전문은 **정리한 뒤에** 남긴다. 순서가 반대면 방금 쓴 로그가 지워진다.
    write_full_log(workdir, log)

    artifacts = tuple(
        path
        for path in (workdir / RESULT_FILENAME, workdir / STREAM_FILENAME)
        if path.exists()
    )
    return DeviceResult(
        exit_code=exit_code,
        log=log,
        timed_out=timed_out,
        errors=tuple(errors),
        dataset=dataset,
        artifacts=artifacts,
        spec_json=source,
    )


def _write_result(workdir: Path, dataset: dict[str, Any] | None) -> None:
    """되살린 결과를 파일로도 남긴다. 산출물 목록이 한 가지로 통일된다."""
    if dataset is None:
        return
    try:
        (workdir / RESULT_FILENAME).write_text(json.dumps(dataset))
    except OSError:
        logger.warning("결과 파일을 쓰지 못했습니다", exc_info=True)


def place_structure(workdir: Path, text: str) -> Path:
    """제출 시점에 `.str` 을 잡 작업디렉토리에 복사한다.

    원본 잡의 산출물은 유휴·쿼터 스윕에 지워질 수 있다. 해석이 시작될 때
    입력이 사라져 있으면 안 되므로 여기서 스냅샷을 뜬다.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / STRUCTURE_FILENAME
    target.write_text(text)
    return target


def copy_structure(workdir: Path, path: Path) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / STRUCTURE_FILENAME
    shutil.copyfile(path, target)
    return target
