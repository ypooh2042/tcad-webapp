"""podman 자체가 못 뜨는 상태를 알아보고 되살린다.

실제 podman 을 건드리지 않는다 — pause.pid 를 가짜로 만들어 판단만 본다.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from app.runner.podman_health import (
    ADVICE,
    looks_like_infra_failure,
    repair,
)

REAL_ERROR = """\
time="2026-08-19T16:34:25+09:00" level=error msg="running `/usr/bin/newuidmap 1072698 0 1000 1 1 100000 65536`: newuidmap: write to uid_map failed: Operation not permitted\\n"
time="2026-08-19T16:34:25+09:00" level=error msg="invalid internal status, try resetting the pause process with \\"podman system migrate\\": cannot set up namespace using \\"/usr/bin/newuidmap\\": exit status 1"
"""


class TestRecognisingTheFailure:
    def test_recognises_the_real_error(self) -> None:
        assert looks_like_infra_failure(125, REAL_ERROR)

    def test_recognises_a_stale_pause_process(self) -> None:
        assert looks_like_infra_failure(
            125, 'cannot join namespace for 1234: Operation not permitted'
        )

    def test_a_successful_run_is_never_infra_failure(self) -> None:
        assert not looks_like_infra_failure(0, REAL_ERROR)

    def test_simulator_crash_is_not_infra_failure(self) -> None:
        """시뮬레이터가 스스로 죽은 것은 다시 돌려도 같다."""
        assert not looks_like_infra_failure(
            139, "suprem4 panic: triangles are not clock wise\n"
        )

    def test_missing_image_is_not_infra_failure(self) -> None:
        """이미지가 없는 것도 125 로 나오지만 되살릴 것이 없다."""
        assert not looks_like_infra_failure(
            125, "Error: short-name resolution enforced but cannot prompt\n"
        )


class TestRepair:
    def test_no_pause_file_means_nothing_to_do(self, tmp_path: Path) -> None:
        # 파일이 없으면 podman 이 알아서 새로 만든다. 손댈 것이 없다.
        assert repair(tmp_path / "pause.pid") is None

    def test_removes_a_pause_file_naming_a_dead_process(
        self, tmp_path: Path
    ) -> None:
        pause = tmp_path / "pause.pid"
        pause.write_text("2147483646\n")  # 존재할 수 없는 pid

        note = repair(pause)

        assert note is not None and "없는" in note
        assert not pause.exists()

    def test_removes_the_file_but_spares_a_healthy_pause_process(
        self, tmp_path: Path
    ) -> None:
        """살아 있는 것은 죽이지 않는다.

        밖에서는 그것이 정말 고장인지 알 수 없다. 파일만 치우면 podman 이 새
        pause 프로세스를 만들고, 남은 것은 무해하다 — 실측으로 확인했다.
        중복 pause 프로세스 일곱 개가 같은 네임스페이스를 정상 매핑으로 잡고
        있었고 컨테이너는 모두 정상이었다.
        """
        pause = tmp_path / "pause.pid"
        pause.write_text(f"{os.getpid()}\n")

        note = repair(pause)

        assert note is not None
        assert not pause.exists()
        # 우리 자신이 아직 살아 있다는 것이 곧 "죽이지 않았다"이다.

    def test_kills_a_pause_process_holding_an_unmapped_namespace(
        self, tmp_path: Path
    ) -> None:
        """매핑 없는 user namespace 를 잡은 것은 확실한 고장이다.

        podman 이 그 안으로 들어가면 아무 권한이 없어 newuidmap 이 EPERM 을
        낸다. 이것만은 밖에서 확실히 판정할 수 있으므로 죽인다.
        """
        if not Path("/proc/self/uid_map").exists():
            pytest.skip("/proc 가 없습니다")
        try:
            victim = subprocess.Popen(  # noqa: S603
                ("unshare", "-U", "sleep", "30"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pytest.skip("unshare 가 없습니다")

        try:
            # unshare 가 자식을 만들 때까지 기다린다.
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if Path(f"/proc/{victim.pid}/uid_map").read_text().strip() == "":
                    break
                time.sleep(0.05)

            pause = tmp_path / "pause.pid"
            pause.write_text(f"{victim.pid}\n")

            note = repair(pause)

            assert note is not None and "매핑" in note
            assert not pause.exists()
            victim.wait(timeout=5)  # 죽었어야 한다
        finally:
            if victim.poll() is None:
                os.kill(victim.pid, signal.SIGKILL)
                victim.wait(timeout=5)

    def test_garbage_in_the_file_is_treated_as_stale(
        self, tmp_path: Path
    ) -> None:
        pause = tmp_path / "pause.pid"
        pause.write_text("깨진 내용")

        assert repair(pause) is not None
        assert not pause.exists()


class TestAdvice:
    def test_advice_warns_against_system_migrate(self) -> None:
        """podman 은 `podman system migrate` 를 권하지만 여기서는 위험하다.

        그 명령은 **도는 컨테이너를 전부 멈춘다.** 이 서버의 postgres 와 redis 는
        systemd 가 관리하지 않아 스스로 돌아오지 않는다.
        """
        assert "system migrate" in ADVICE


class TestRunnerRetriesOnce:
    """러너가 기반 실패를 스스로 넘기는가.

    실제 podman 을 고장 내지 않고 `_execute` 만 갈아끼워 확인한다.
    """

    INFRA = (125, REAL_ERROR, False, False)
    OK = (0, "SUPREM-IV.GS B.9305\n", False, False)

    def _patch(self, monkeypatch, outcomes, note="치웠습니다"):
        from app.runner import runner as mod

        calls: list[int] = []

        def fake_execute(workdir, image, limits):
            calls.append(1)
            return outcomes[min(len(calls) - 1, len(outcomes) - 1)]

        monkeypatch.setattr(mod, "_execute", fake_execute)
        monkeypatch.setattr(mod, "repair_podman", lambda: note)
        return calls

    def test_repairs_and_retries(self, monkeypatch, tmp_path) -> None:
        from app.runner.runner import RETRIED_NOTICE, run_simulation

        calls = self._patch(monkeypatch, [self.INFRA, self.OK])
        result = run_simulation("initialize\n", tmp_path / "job")

        assert len(calls) == 2, "되살린 뒤 정확히 한 번 더 돌려야 합니다"
        assert result.succeeded
        assert RETRIED_NOTICE in result.log
        # 첫 실패의 원문도 남아야 한다 — 지우면 무슨 일이었는지 알 수 없다.
        assert "newuidmap" in result.log

    def test_gives_up_after_one_retry(self, monkeypatch, tmp_path) -> None:
        """되살려도 안 되면 두 번째 재시도는 없다."""
        from app.runner.podman_health import ADVICE
        from app.runner.runner import run_simulation

        calls = self._patch(monkeypatch, [self.INFRA])
        result = run_simulation("initialize\n", tmp_path / "job")

        assert len(calls) == 2
        assert not result.succeeded
        assert any(ADVICE in e for e in result.errors), result.errors

    def test_does_not_retry_when_there_is_nothing_to_repair(
        self, monkeypatch, tmp_path
    ) -> None:
        """되살릴 것이 없으면 원인이 다른 곳이다. 시간만 쓰지 않는다."""
        from app.runner.runner import run_simulation

        calls = self._patch(monkeypatch, [self.INFRA], note=None)
        run_simulation("initialize\n", tmp_path / "job")

        assert len(calls) == 1

    def test_a_simulator_failure_is_not_retried(
        self, monkeypatch, tmp_path
    ) -> None:
        """시뮬레이터가 죽은 것은 다시 돌려도 같다 — 여기서 만지면 안 된다."""
        from app.runner.runner import run_simulation

        panic = (139, "suprem4 panic: triangles are not clock wise\n", False, False)
        calls = self._patch(monkeypatch, [panic])
        run_simulation("initialize\n", tmp_path / "job")

        assert len(calls) == 1
