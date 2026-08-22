"""수렴에 실패한 점을 건너뛰고 이어 가기.

점 하나가 안 풀렸다고 해석을 통째로 버리지 않는다. 스윕 끝쪽 몇 점이 발산하는
것은 흔한 일이고 그 앞의 곡선은 멀쩡하다. 대신 어느 점이 빠졌는지는 반드시
알려야 한다 — 조용히 빼면 사용자는 그 자리에 값이 없다는 것도 모른 채 곡선을
읽는다.
"""

import json

from app.devsim.service import (
    RESULT_FILENAME,
    STREAM_FILENAME,
    DeviceResult,
    _read_dataset,
)


def line(sweep: float, ok: bool, reason: str | None = None) -> str:
    row: dict = {"sweep": sweep, "steps": {"Vg": 1.0}}
    if ok:
        row["currents"] = {"Vd": 1e-6}
        row["ok"] = True
    else:
        row["ok"] = False
        row["reason"] = reason or "Convergence failure!"
    return json.dumps(row)


class TestReadDataset:
    def test_reads_the_finished_result(self, tmp_path) -> None:
        (tmp_path / RESULT_FILENAME).write_text(
            json.dumps({"rows": [], "failures": [], "completed": 0, "total": 3})
        )
        found = _read_dataset(tmp_path, total=3)
        assert found is not None
        assert found["failures"] == []

    def test_rebuilds_from_the_stream_when_the_run_is_cut_short(
        self, tmp_path
    ) -> None:
        # 컨테이너가 상한이나 타임아웃으로 죽으면 iv.json 을 못 쓴다. 그래도
        # 거기까지 푼 점은 흘려보낸 줄에 남아 있다.
        (tmp_path / STREAM_FILENAME).write_text(
            "\n".join([line(0.0, True), line(0.5, False), line(1.0, True)]) + "\n"
        )
        found = _read_dataset(tmp_path, total=3)
        assert found is not None
        assert found["completed"] == 2
        assert [row["sweep"] for row in found["rows"]] == [0.0, 1.0]

    def test_keeps_the_skipped_points_apart_from_the_curve(self, tmp_path) -> None:
        (tmp_path / STREAM_FILENAME).write_text(
            "\n".join([line(0.0, True), line(0.5, False, "발산")]) + "\n"
        )
        found = _read_dataset(tmp_path, total=2)
        assert found is not None
        assert [f["sweep"] for f in found["failures"]] == [0.5]
        assert found["failures"][0]["reason"] == "발산"
        # 실패한 점이 곡선에 섞이면 그래프가 0 으로 뚝 떨어진다.
        assert all("currents" in row for row in found["rows"])

    def test_nothing_at_all_is_nothing(self, tmp_path) -> None:
        assert _read_dataset(tmp_path, total=3) is None


class TestSucceeded:
    """건너뛴 점이 있어도 실패가 아니다."""

    def _result(self, rows: int, failures: int) -> DeviceResult:
        return DeviceResult(
            exit_code=0,
            log="",
            timed_out=False,
            errors=(),
            dataset={
                "rows": [{}] * rows,
                "failures": [{}] * failures,
                "completed": rows,
                "total": rows + failures,
            },
            artifacts=(),
        )

    def test_a_full_run_succeeds(self) -> None:
        assert self._result(15, 0).succeeded is True

    def test_a_partial_run_still_succeeds(self) -> None:
        # 사용자가 볼 곡선이 남아 있다.
        assert self._result(11, 4).succeeded is True

    def test_nothing_solved_is_a_failure(self) -> None:
        assert self._result(0, 15).succeeded is False


class TestMovingMarkers:
    """곡선 사이를 옮기는 표시는 곡선에도 실패에도 들어가지 않는다."""

    def test_ignored_when_rebuilding_from_the_stream(self, tmp_path) -> None:
        (tmp_path / STREAM_FILENAME).write_text(
            "\n".join(
                [
                    json.dumps({"phase": "moving", "steps": {"Vg": 1.0}}),
                    line(0.0, True),
                    json.dumps({"phase": "moving", "steps": {"Vg": 2.0}}),
                    line(0.5, True),
                ]
            )
            + "\n"
        )
        found = _read_dataset(tmp_path, total=2)
        assert found is not None
        assert found["completed"] == 2
        assert found["failures"] == []

    def test_only_markers_is_nothing(self, tmp_path) -> None:
        (tmp_path / STREAM_FILENAME).write_text(
            json.dumps({"phase": "moving", "steps": {}}) + "\n"
        )
        assert _read_dataset(tmp_path, total=2) is None


class TestRemeshRunsInTheJobDirectory:
    """재메시도 잡의 컨테이너 이름으로 돌아야 한다.

    중단 버튼은 작업디렉토리 이름에서 컨테이너 이름을 만들어 죽인다
    (`sandbox.container_name`). 재메시가 임시 디렉토리에서 돌면 이름이 어긋나,
    재메시가 도는 동안(실측 12초, 큰 구조는 더) 중단이 먹지 않는다.
    """

    def test_uses_the_workdir_it_is_given(self, tmp_path, monkeypatch) -> None:
        from pathlib import Path

        import app.devsim.service as service

        seen: dict[str, Path | None] = {}

        def fake_remesh(source, image=None, workdir=None, **rest):
            seen["workdir"] = workdir
            raise OSError("여기까지만 본다")

        monkeypatch.setattr(service, "remesh", fake_remesh)
        (tmp_path / service.STRUCTURE_FILENAME).write_text("v x\n")

        spec = json.dumps(
            {
                "electrodes": [{"label": "a", "interfaces": ["source"]}],
                "biases": [
                    {
                        "name": "V",
                        "electrode": "a",
                        "role": "sweep",
                        "sweep": {"start": 0.0, "stop": 1.0, "points": 2},
                    }
                ],
            }
        )
        service.run_device_simulation(spec, tmp_path)
        assert seen["workdir"] == tmp_path


class TestDeviceTimeout:
    """소자 해석 상한은 **큰 구조**를 기준으로 잡아야 한다.

    실측 두 가지:
      nmos.in  재메시 후  8,143 노드 — 바이어스 점당 약 1.6 초
      cmos.in  재메시 후 50,062 노드 — 바이어스 점당 약  20 초

    직접 솔버라 노드 수에 대해 초선형으로 는다(6.1 배 노드에 12.5 배 시간).
    900 초로는 큰 구조에서 45 점밖에 못 돌린다 — 실제로 42 점짜리 인버터
    부하선이 중간에 잘렸다.
    """

    #: 이 구조에서 실측한 점당 시간(초).
    SECONDS_PER_POINT_ON_A_BIG_STRUCTURE = 20

    def test_allows_a_full_sweep_on_the_big_structure(self) -> None:
        from app.devsim.service import DEFAULT_LIMITS
        from app.devsim.spec import MAX_TOTAL_POINTS

        needed = MAX_TOTAL_POINTS * self.SECONDS_PER_POINT_ON_A_BIG_STRUCTURE
        assert DEFAULT_LIMITS.timeout_seconds >= needed, (
            f"상한을 다 쓴 해석이 {needed} 초 걸리는데 "
            f"{DEFAULT_LIMITS.timeout_seconds} 초에서 잘립니다"
        )

    def test_is_longer_than_the_suprem_default(self) -> None:
        """공정 실행보다 길어야 한다. 짧으면 큰 해석이 늘 잘린다."""
        from app.core.config import Settings
        from app.devsim.service import DEFAULT_LIMITS

        assert DEFAULT_LIMITS.timeout_seconds > Settings().job_timeout_seconds


class TestPodmanRecoveryDuringPreparation:
    """준비 단계(재메시)에서 podman 기반이 무너지면 되살리고 한 번 더 해 본다.

    공정 실행(`app/runner/runner.py`)에는 이 복구가 있었는데 소자 해석에는
    없었다. 그래서 pause 프로세스가 죽은 사이 해석을 돌리면 재메시가
    `RuntimeError` 로 죽고, 그것이 아무 데서도 안 잡혀 사용자에게는
    **"워커에서 예기치 못한 오류가 발생했습니다"** 만 보였다 — 무엇이
    잘못됐는지도, 다시 하면 되는지도 알 수 없는 문구다.
    """

    INFRA = (
        "gmsh 가 메시를 만들지 못했습니다\n"
        "newuidmap: write to uid_map failed: Operation not permitted"
    )

    def _spec(self) -> str:
        return json.dumps(
            {
                "electrodes": [{"label": "a", "interfaces": ["source"]}],
                "biases": [
                    {
                        "name": "V",
                        "electrode": "a",
                        "role": "sweep",
                        "sweep": {"start": 0.0, "stop": 1.0, "points": 2},
                    }
                ],
            }
        )

    def test_repairs_and_tries_again(self, tmp_path, monkeypatch) -> None:
        import app.devsim.service as service

        (tmp_path / service.STRUCTURE_FILENAME).write_text("v x\n")
        calls = []

        def flaky(workdir, spec):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError(self.INFRA)
            raise OSError("여기까지만 본다")

        monkeypatch.setattr(service, "_prepare_device", flaky)
        monkeypatch.setattr(service, "repair_podman", lambda: "치웠습니다")
        monkeypatch.setattr(service, "ensure_pause_process", lambda: None)

        service.run_device_simulation(self._spec(), tmp_path)

        assert len(calls) == 2, "되살린 뒤 한 번 더 해 봐야 합니다"

    def test_only_once(self, tmp_path, monkeypatch) -> None:
        """되살려도 안 되면 두 번째 재시도는 없다. 잡 슬롯만 묶인다."""
        import app.devsim.service as service

        (tmp_path / service.STRUCTURE_FILENAME).write_text("v x\n")
        calls = []

        def always(workdir, spec):
            calls.append(1)
            raise RuntimeError(self.INFRA)

        monkeypatch.setattr(service, "_prepare_device", always)
        monkeypatch.setattr(service, "repair_podman", lambda: "치웠습니다")
        monkeypatch.setattr(service, "ensure_pause_process", lambda: None)

        result = service.run_device_simulation(self._spec(), tmp_path)

        assert len(calls) == 2
        assert not result.succeeded
        assert any(service.ADVICE in e for e in result.errors), result.errors

    def test_a_real_mesh_failure_is_not_retried(self, tmp_path, monkeypatch) -> None:
        """형상 때문에 실패한 것은 다시 해도 같다. 시간만 쓴다."""
        import app.devsim.service as service

        (tmp_path / service.STRUCTURE_FILENAME).write_text("v x\n")
        calls = []

        def broken(workdir, spec):
            calls.append(1)
            raise RuntimeError("gmsh 가 메시를 만들지 못했습니다\nInvalid boundary mesh")

        monkeypatch.setattr(service, "_prepare_device", broken)

        result = service.run_device_simulation(self._spec(), tmp_path)

        assert len(calls) == 1
        assert not result.succeeded

    def test_the_message_says_what_happened(self, tmp_path, monkeypatch) -> None:
        """catch-all 로 새어 나가면 안 된다. 사용자가 읽을 문구가 있어야 한다."""
        import app.devsim.service as service

        (tmp_path / service.STRUCTURE_FILENAME).write_text("v x\n")
        monkeypatch.setattr(
            service,
            "_prepare_device",
            lambda w, s: (_ for _ in ()).throw(RuntimeError("메시가 깨졌습니다")),
        )

        result = service.run_device_simulation(self._spec(), tmp_path)

        assert not result.succeeded
        assert any("메시가 깨졌습니다" in e for e in result.errors), result.errors


class TestPodmanRecoveryDuringExecution:
    """컨테이너 실행 단계도 마찬가지다.

    예전에는 기반 실패를 알아보고도 **안내 문구만 붙이고 끝**이었다. 되살리면
    되는 상황인데 사용자가 직접 다시 눌러야 했다.
    """

    INFRA_LOG = (
        'invalid internal status, try resetting the pause process with '
        '"podman system migrate"'
    )

    def _spec(self) -> str:
        return json.dumps(
            {
                "electrodes": [{"label": "a", "interfaces": ["source"]}],
                "biases": [
                    {
                        "name": "V",
                        "electrode": "a",
                        "role": "sweep",
                        "sweep": {"start": 0.0, "stop": 1.0, "points": 2},
                    }
                ],
            }
        )

    def _patch(self, monkeypatch, tmp_path, outcomes):
        import app.devsim.service as service

        (tmp_path / service.STRUCTURE_FILENAME).write_text("v x\n")
        monkeypatch.setattr(service, "_prepare_device", lambda w, s: 2)
        monkeypatch.setattr(service, "_read_dataset", lambda w, t: None)
        monkeypatch.setattr(service, "repair_podman", lambda: "치웠습니다")
        monkeypatch.setattr(service, "ensure_pause_process", lambda: None)

        calls = []

        def fake_execute(workdir, image, limits):
            calls.append(1)
            return outcomes[min(len(calls) - 1, len(outcomes) - 1)]

        monkeypatch.setattr(service, "_execute", fake_execute)
        return service, calls

    def test_repairs_and_runs_again(self, tmp_path, monkeypatch) -> None:
        service, calls = self._patch(
            monkeypatch, tmp_path, [(125, self.INFRA_LOG, False), (0, "ok", False)]
        )

        service.run_device_simulation(self._spec(), tmp_path)

        assert len(calls) == 2, "되살린 뒤 한 번 더 돌려야 합니다"

    def test_only_once(self, tmp_path, monkeypatch) -> None:
        service, calls = self._patch(
            monkeypatch, tmp_path, [(125, self.INFRA_LOG, False)]
        )

        result = service.run_device_simulation(self._spec(), tmp_path)

        assert len(calls) == 2
        assert any(service.ADVICE in e for e in result.errors), result.errors

    def test_a_solver_failure_is_not_retried(self, tmp_path, monkeypatch) -> None:
        """해석이 발산한 것은 다시 돌려도 같다."""
        service, calls = self._patch(
            monkeypatch, tmp_path, [(1, "Convergence failure!", False)]
        )

        service.run_device_simulation(self._spec(), tmp_path)

        assert len(calls) == 1
