"""샌드박스 실행 인자 구성 테스트.

이 테스트들은 편의 기능이 아니라 보안 경계를 지키는 회귀 테스트다.
SUPREM4GS 는 인식하지 못한 첫 단어를 /bin/bash 로 넘기므로, 사용자가 제출하는
.in 파일은 그 자체로 임의 셸 스크립트다. 아래 제약 중 하나라도 조용히 빠지면
서비스가 곧바로 원격 코드 실행 창구가 된다.
"""

from pathlib import Path

import pytest

from app.runner.sandbox import (
    SANDBOX_WORKDIR,
    SOURCE_FILENAME,
    SandboxLimits,
    build_sandbox_argv,
    build_stdin_script,
)

WORKDIR = Path("/var/lib/tcad/jobs/abc123")


@pytest.fixture
def argv() -> tuple[str, ...]:
    return build_sandbox_argv(
        image="tcad/suprem:latest",
        host_workdir=WORKDIR,
        limits=SandboxLimits(),
    )


class TestIsolation:
    def test_network_is_disabled(self, argv) -> None:
        """네트워크가 열려 있으면 탈취한 셸로 외부 통신이 가능해진다."""
        assert "--network" in argv
        assert argv[argv.index("--network") + 1] == "none"

    def test_all_capabilities_dropped(self, argv) -> None:
        assert "--cap-drop" in argv
        assert argv[argv.index("--cap-drop") + 1] == "ALL"

    def test_privilege_escalation_blocked(self, argv) -> None:
        """setuid 바이너리를 통한 권한 상승을 막는다."""
        assert "no-new-privileges" in " ".join(argv)

    def test_root_filesystem_is_read_only(self, argv) -> None:
        assert "--read-only" in argv

    def test_runs_as_non_root_user(self, argv) -> None:
        assert "--user" in argv
        uid = argv[argv.index("--user") + 1]
        assert not uid.startswith("0:")
        assert uid != "0"

    def test_uid_is_mapped_so_scratch_dir_is_accessible(self, argv) -> None:
        """루트리스 Podman 기본 매핑에서는 컨테이너가 스크래치를 못 읽는다.

        keep-id 로 호스트 유저를 컨테이너 실행 uid 에 직접 매핑해야
        입력을 읽고 결과를 쓸 수 있다(실측으로 확인한 실패 모드).
        """
        assert "--userns" in argv
        assert argv[argv.index("--userns") + 1] == "keep-id:uid=10001,gid=10001"

    def test_container_is_removed_after_run(self, argv) -> None:
        """잡 산출물이 컨테이너 레이어에 남지 않도록."""
        assert "--rm" in argv


class TestResourceLimits:
    def test_memory_limit_applied(self, argv) -> None:
        assert "--memory" in argv

    def test_cpu_limit_applied(self, argv) -> None:
        assert "--cpus" in argv

    def test_pids_limit_applied(self, argv) -> None:
        """fork 폭탄 방어."""
        assert "--pids-limit" in argv

    def test_limits_are_configurable(self) -> None:
        argv = build_sandbox_argv(
            image="tcad/suprem:latest",
            host_workdir=WORKDIR,
            limits=SandboxLimits(cpus=2.0, memory_mb=512, max_pids=64),
        )
        assert argv[argv.index("--cpus") + 1] == "2.0"
        assert argv[argv.index("--memory") + 1] == "512m"
        assert argv[argv.index("--pids-limit") + 1] == "64"


class TestWorkdirMount:
    def test_scratch_dir_mounted_read_write(self, argv) -> None:
        mount = next(a for a in argv if str(WORKDIR) in a)
        assert mount == f"{WORKDIR}:{SANDBOX_WORKDIR}:rw"

    def test_only_one_bind_mount(self, argv) -> None:
        """스크래치 디렉토리 외에 호스트 경로가 새어 들어가면 안 된다."""
        assert sum(1 for a in argv if a in ("-v", "--volume")) == 1

    def test_rejects_relative_host_path(self) -> None:
        """상대 경로는 실행 시점 cwd 에 따라 엉뚱한 곳을 마운트할 수 있다."""
        with pytest.raises(ValueError, match="절대 경로"):
            build_sandbox_argv(
                image="tcad/suprem:latest",
                host_workdir=Path("relative/dir"),
                limits=SandboxLimits(),
            )


class TestUserInputNeverReachesArgv:
    """가장 중요한 불변식: 사용자 입력은 인자에 절대 들어가지 않는다.

    소스 코드는 스크래치 디렉토리 안의 고정된 파일명으로 기록되고, 컨테이너에는
    그 고정 파일명만 전달된다. 사용자 문자열이 argv 로 흘러들면 인자 주입이 된다.
    """

    def test_argv_does_not_depend_on_source_text(self) -> None:
        first = build_sandbox_argv("img", WORKDIR, SandboxLimits())
        second = build_sandbox_argv("img", WORKDIR, SandboxLimits())
        assert first == second

    def test_stdin_script_is_fixed_regardless_of_source(self) -> None:
        malicious = "quit\nrm -rf /\nsource /etc/shadow"
        assert build_stdin_script() == build_stdin_script()
        assert malicious not in build_stdin_script()

    def test_stdin_script_references_only_fixed_filename(self) -> None:
        script = build_stdin_script()
        assert f"source {SOURCE_FILENAME}" in script
        assert script.strip().endswith("quit")


class TestImmutability:
    def test_limits_are_frozen(self) -> None:
        limits = SandboxLimits()
        with pytest.raises(Exception):
            limits.cpus = 99.0  # type: ignore[misc]

    def test_argv_is_immutable_sequence(self, argv) -> None:
        assert isinstance(argv, tuple)
