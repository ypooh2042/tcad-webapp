"""러너 통합 테스트 — 실제 Podman 컨테이너를 띄운다.

여기 있는 테스트 중 상당수는 기능 테스트가 아니라 **격리 검증**이다.
SUPREM4GS 는 인식하지 못한 첫 단어를 /bin/bash 로 넘기므로, 사용자가 제출한
`.in` 은 임의 셸 스크립트다. 아래 항목이 하나라도 깨지면 서비스를 열면 안 된다.

실행: podman 과 tcad/suprem:latest 이미지가 필요하다. 없으면 자동 skip 된다.
"""

from __future__ import annotations

import getpass
import shutil
import subprocess
from pathlib import Path

import pytest

from app.runner.runner import DEFAULT_IMAGE, run_simulation
from app.runner.sandbox import SandboxLimits
from app.str_parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"

pytestmark = pytest.mark.integration


def _image_available() -> bool:
    if shutil.which("podman") is None:
        return False
    probe = subprocess.run(
        ["podman", "image", "exists", DEFAULT_IMAGE], check=False
    )
    return probe.returncode == 0


requires_sandbox = pytest.mark.skipif(
    not _image_available(),
    reason="podman 또는 tcad/suprem:latest 이미지가 없습니다",
)


@requires_sandbox
class TestSuccessfulRun:
    def test_produces_structure_file(self, tmp_path: Path) -> None:
        source = (FIXTURES / "1d_multi_dopant.in").read_text()
        result = run_simulation(source, tmp_path / "job")

        assert result.succeeded
        assert len(result.structure_files) == 1
        assert result.structure_files[0].name == "multi.str"

    def test_output_parses_and_matches_golden_fixture(self, tmp_path: Path) -> None:
        """샌드박스 결과가 호스트에서 직접 돌린 골든 파일과 같아야 한다."""
        source = (FIXTURES / "1d_multi_dopant.in").read_text()
        result = run_simulation(source, tmp_path / "job")

        produced = parse_structure(result.structure_files[0].read_text())
        golden = parse_structure((FIXTURES / "1d_multi_dopant.str").read_text())

        assert [s.name for s in produced.species] == [s.name for s in golden.species]
        assert len(produced.coordinates) == len(golden.coordinates)
        assert produced.solutions[0].values == golden.solutions[0].values

    def test_results_are_readable_by_host(self, tmp_path: Path) -> None:
        """루트리스 uid 매핑이 틀리면 결과 파일을 호스트가 못 읽는다."""
        source = (FIXTURES / "1d_multi_dopant.in").read_text()
        result = run_simulation(source, tmp_path / "job")

        assert result.structure_files[0].read_text().startswith("v SUPREM")


@requires_sandbox
class TestErrorReporting:
    def test_command_errors_are_detected_despite_exit_zero(
        self, tmp_path: Path
    ) -> None:
        """시뮬레이터는 커맨드 오류가 있어도 exit 0 으로 끝난다.

        종료 코드만 믿으면 실패한 잡을 성공으로 보고하게 된다.
        """
        source = "option plot.out=output.ps device=postcript\nquit\n"
        result = run_simulation(source, tmp_path / "job")

        assert result.exit_code == 0
        assert result.errors
        assert not result.succeeded


@requires_sandbox
class TestIsolation:
    """적대적 `.in` 이 셸 fall-through 로 무엇을 할 수 있는지 실제로 시도한다."""

    def _run(self, tmp_path: Path, script: str):
        return run_simulation(f"{script}\nquit\n", tmp_path / "job")

    def test_cannot_reach_network(self, tmp_path: Path) -> None:
        """도구 부재가 아니라 네트워크 자체가 없어야 한다."""
        result = self._run(
            tmp_path,
            "bash -c 'exec 3<>/dev/tcp/1.1.1.1/53 && echo REACHED || echo BLOCKED'",
        )
        assert "REACHED" not in result.log
        assert "Network is unreachable" in result.log

    def test_only_loopback_interface_exists(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, "cat /proc/net/dev")
        assert "lo:" in result.log
        assert "eth0" not in result.log

    def test_runs_as_unprivileged_user(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, "id")
        assert "uid=10001" in result.log
        assert "uid=0(root)" not in result.log

    def test_cannot_see_host_home_directories(self, tmp_path: Path) -> None:
        """호스트 홈 디렉토리가 컨테이너에 보이면 안 된다.

        유저명은 실행 시점에 구해서 쓴다. 소스에 박아두면 레포에 개인 정보가
        남고, 다른 환경에서 테스트가 무의미해진다.
        """
        host_user = getpass.getuser()
        result = self._run(tmp_path, "ls /home")
        assert host_user not in result.log

    def test_cannot_read_shadow_file(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, "cat /etc/shadow")
        assert "Permission denied" in result.log

    def test_cannot_tamper_with_simulator_binary(self, tmp_path: Path) -> None:
        """바이너리를 고쳐 쓰면 다음 사용자의 실행을 오염시킬 수 있다."""
        result = self._run(tmp_path, "touch /opt/suprem4gs/pwned")
        assert "Read-only file system" in result.log

    def test_cannot_escape_scratch_directory(self, tmp_path: Path) -> None:
        """`structure out=` 으로 상위 경로에 쓰려는 시도."""
        outside = tmp_path / "outside.str"
        self._run(tmp_path, f"structure out={outside}")
        assert not outside.exists()

    def test_writes_stay_inside_scratch_directory(self, tmp_path: Path) -> None:
        workdir = tmp_path / "job"
        # 산출물 확장자로 만든다. 러너가 실행 후 `.str` 이 아닌 파일을 지우기
        # 때문이다(디스크가 무한정 늘지 않게 하는 조치).
        self._run(tmp_path, "touch /work/marker.str")
        assert (workdir / "marker.str").exists()


@requires_sandbox
class TestResourceLimits:
    def test_runaway_job_is_killed_by_timeout(self, tmp_path: Path) -> None:
        result = run_simulation(
            "bash -c 'sleep 300'\nquit\n",
            tmp_path / "job",
            limits=SandboxLimits(timeout_seconds=10),
        )
        assert result.timed_out or result.exit_code != 0
        assert not result.succeeded
