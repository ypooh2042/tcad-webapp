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


@requires_sandbox
class TestDenseGridSurvivesOxidation:
    """격자를 촘촘히 깔면 죽던 문제.

    시뮬레이터의 희소행렬 작업공간은 realloc 으로 두 배씩 커지는 자체 풀인데,
    `min_ia_fill` 이 그 realloc **뒤에도 호출 전에 구한 포인터를 계속 쓴다.**
    1993년 malloc 은 큰 블록도 힙에서 잡아 대개 제자리 확장이라 이 버그가
    잠들어 있었지만, 현대 glibc 는 큰 할당을 mmap 으로 돌리고 늘릴 때 주소를
    옮겨 버그를 깨운다. 컨테이너가 MALLOC_MMAP_THRESHOLD_ 를 올려 피한다.

    이 테스트는 그 환경변수가 이미지에서 빠지면 빨간불이 된다.
    """

    def test_dense_surface_grid_completes_oxidation(self, tmp_path: Path) -> None:
        source = (FIXTURES / "2d_dense_surface_grid.in").read_text()

        result = run_simulation(source, tmp_path / "job")

        assert result.succeeded, result.log[-2000:]
        assert [f.name for f in result.structure_files] == ["oxidation.str"]

    def test_grid_that_the_malloc_workaround_could_not_save(
        self, tmp_path: Path
    ) -> None:
        """환경변수 완화로는 부족했던 격자.

        컨테이너의 MALLOC_MMAP_THRESHOLD_ 는 realloc 이 제자리에서 늘어나도록
        유도할 뿐이라, 힙 상태에 따라 여전히 블록이 옮겨진다. 이 격자가 실제로
        그랬다(완화를 걸고도 5회 연속 죽음). 소스 패치가 빠지면 다시 죽는다.
        """
        source = (FIXTURES / "2d_wide_uniform_grid.in").read_text()

        result = run_simulation(source, tmp_path / "job")

        assert result.succeeded, result.log[-2000:]

    def test_oxide_actually_grew(self, tmp_path: Path) -> None:
        """죽지 않는 것만으로는 부족하다 — 결과가 물리적으로 맞아야 한다."""
        source = (FIXTURES / "2d_dense_surface_grid.in").read_text()

        result = run_simulation(source, tmp_path / "job")
        structure = parse_structure(result.structure_files[0].read_text())

        materials = {r.material for r in structure.regions}
        assert "oxide" in materials

        by_region = {r.id: r.material for r in structure.regions}
        oxide_y = [
            structure.coordinates[v].y
            for element in structure.elements
            if by_region[element.region_id] == "oxide"
            for v in element.vertices
        ]
        # 1050도 건식산화 5분이면 20nm 안팎이다. 자릿수가 어긋나면 결과가 깨진 것이다.
        thickness = max(oxide_y) - min(oxide_y)
        assert 0.005 < thickness < 0.05, thickness


@requires_sandbox
class TestGridLimitIsExplained:
    """상한을 넘겼을 때 사용자가 이유를 알 수 있는가.

    이 격자는 고칠 수 없다 — 시뮬레이터 안의 16비트 카운터가 넘친다. 고칠 수
    없다면 **최소한 왜 실패했는지는 말해 줘야 한다.** 세그폴트는 로그를 통째로
    날리므로 그냥 두면 화면에 아무 단서도 남지 않는다.
    """

    def test_failure_names_the_grid_size(self, tmp_path: Path) -> None:
        source = (FIXTURES / "2d_over_grid_limit.in").read_text()

        result = run_simulation(source, tmp_path / "job")

        assert not result.succeeded
        joined = " ".join(result.errors)
        assert "격자" in joined, joined
        # 실제로 만든 점 개수를 알려 줘야 얼마나 줄일지 판단할 수 있다.
        assert "점입니다" in joined, joined


@requires_sandbox
class TestCancellingARunningJob:
    """도는 컨테이너를 밖에서 멈출 수 있는가.

    중단 버튼은 워커가 아니라 API 프로세스가 처리한다. 컨테이너 이름이 workdir
    에서 결정론적으로 나오기 때문에 가능한 구조인데, 그 전제가 깨지면 버튼이
    조용히 아무 일도 하지 않는다.
    """

    def test_kill_stops_the_container_and_the_runner(self, tmp_path: Path) -> None:
        import subprocess
        import threading
        import time

        from app.runner.control import kill_container
        from app.runner.sandbox import container_name

        # 인식하지 못한 첫 단어는 셸로 넘어간다. 오래 도는 잡을 만드는 가장
        # 확실한 방법이고, 그 통로 자체가 격리 테스트의 전제이기도 하다.
        workdir = tmp_path / "job-cancel"
        outcome: dict[str, object] = {}
        worker = threading.Thread(
            target=lambda: outcome.update(result=run_simulation("sleep 120\n", workdir)),
            daemon=True,
        )
        worker.start()

        name = container_name(workdir)
        for _ in range(60):
            time.sleep(0.5)
            running = subprocess.run(
                ("podman", "ps", "--filter", f"name={name}", "--format", "{{.Names}}"),
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            if running:
                break
        assert running, "컨테이너가 뜨지 않았습니다"

        assert kill_container(name) is True

        worker.join(timeout=30)
        assert not worker.is_alive(), "죽였는데도 러너가 끝나지 않았습니다"
        result = outcome["result"]
        assert not result.succeeded
        # 128+9. 신호로 죽은 것이므로 사용자에게 그렇다고 알려야 한다.
        assert result.exit_code == 137

    def test_killing_a_missing_container_is_not_an_error(self) -> None:
        """이미 끝난 잡을 중단해도 서버가 터지면 안 된다."""
        from app.runner.control import kill_container

        assert kill_container("tcad-job-does-not-exist") is False
