"""출력 크기 상한이 실제로 컨테이너를 멈추는지.

설정만 보고 넘어가면 안 되는 항목이다. 실측으로 확인한 문제였다 — 상한이 없던
때 잡 하나가 몇 초 만에 호스트 디스크에 200MB 를 썼고 아무도 막지 않았다.
타임아웃 600초 × NVMe 쓰기 속도면 여유 공간을 전부 채워, 이 홈서버에서 같이
도는 다른 서비스까지 함께 죽는다.

실제 podman 컨테이너를 띄운다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.runner.runner import DEFAULT_IMAGE, run_simulation
from app.runner.sandbox import SandboxLimits
from app.runner.workdir import directory_size

pytestmark = pytest.mark.integration


def require_podman_image() -> None:
    if shutil.which("podman") is None:
        pytest.skip("podman 이 없습니다")


@pytest.fixture
def limits() -> SandboxLimits:
    # 상한을 낮춰 잡아야 테스트가 몇 초 안에 끝난다.
    return SandboxLimits(timeout_seconds=90, max_output_mb=8)


class TestOutputLimit:
    def test_oversized_write_is_stopped(self, tmp_path: Path, limits) -> None:
        """상한을 넘기려 들면 실행을 중단해야 한다."""
        require_podman_image()
        workdir = tmp_path / "job-oversize"

        # SUPREM 은 인식하지 못한 첫 단어를 /bin/bash 로 넘긴다. 사용자가 실제로
        # 쓸 수 있는 경로 그대로다.
        result = run_simulation(
            "dd if=/dev/zero of=/work/filler bs=1M count=400 2>/dev/null\n",
            workdir,
            image=DEFAULT_IMAGE,
            limits=limits,
        )

        assert not result.succeeded

    def test_reports_the_reason(self, tmp_path: Path, limits) -> None:
        """왜 실패했는지 알려주지 않으면 사용자는 원인을 찾을 수 없다."""
        require_podman_image()

        result = run_simulation(
            "dd if=/dev/zero of=/work/filler bs=1M count=400 2>/dev/null\n",
            tmp_path / "job-reason",
            image=DEFAULT_IMAGE,
            limits=limits,
        )

        assert any("상한" in error for error in result.errors)

    def test_disk_is_reclaimed(self, tmp_path: Path, limits) -> None:
        """중단한 뒤에도 쓰다 만 파일이 남으면 디스크는 그대로 차 있다."""
        require_podman_image()
        workdir = tmp_path / "job-reclaim"

        run_simulation(
            "dd if=/dev/zero of=/work/filler bs=1M count=400 2>/dev/null\n",
            workdir,
            image=DEFAULT_IMAGE,
            limits=limits,
        )

        assert directory_size(workdir) < 1_048_576

    def test_normal_run_is_unaffected(self, tmp_path: Path, limits) -> None:
        """정상 잡까지 막으면 안 된다."""
        require_podman_image()
        workdir = tmp_path / "job-normal"

        result = run_simulation(
            "mode one.dim\n"
            "line x loc = 0   spacing = 0.1 tag = top\n"
            "line x loc = 1.0 spacing = 0.1 tag = bottom\n"
            "region silicon xlo = top xhi = bottom\n"
            "bound exposed xlo = top xhi = top\n"
            "init boron conc=1e15\n"
            "structure outfile=out.str\n",
            workdir,
            image=DEFAULT_IMAGE,
            limits=limits,
        )

        assert result.succeeded, result.log
        assert len(result.structure_files) == 1


class TestPruning:
    def test_non_artifacts_are_removed(self, tmp_path: Path, limits) -> None:
        """산출물이 아닌 파일을 남기면 잡이 쌓일수록 디스크가 계속 는다."""
        require_podman_image()
        workdir = tmp_path / "job-prune"

        run_simulation(
            "dd if=/dev/zero of=/work/scratch.bin bs=1M count=2 2>/dev/null\n",
            workdir,
            image=DEFAULT_IMAGE,
            limits=limits,
        )

        assert not (workdir / "scratch.bin").exists()
        assert not (workdir / "job.in").exists()
