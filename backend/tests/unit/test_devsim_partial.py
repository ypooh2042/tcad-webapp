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
