"""DevSim 잡의 진행률과 산출물 보존.

두 가지가 SUPREM 잡과 다르다.

1. 진행률을 `.str` 개수로 못 센다. `structure out=` 이 없기 때문이다. 대신
   해석기가 바이어스 점마다 흘려보내는 `iv.jsonl` 의 줄을 센다.
2. 작업디렉토리 청소가 `.str` 만 남긴다. 그대로 두면 **결과 파일이 지워진다.**
"""

import json
from pathlib import Path

from app.devsim.progress import scan_devsim_progress
from app.runner.workdir import DEVSIM_ARTIFACTS, prune_workdir


def write_stream(workdir: Path, count: int) -> None:
    lines = [
        json.dumps({"sweep": i * 0.5, "steps": {}, "currents": {"Vd": 1e-6}})
        for i in range(count)
    ]
    (workdir / "iv.jsonl").write_text("\n".join(lines) + "\n")


class TestScanDevsimProgress:
    def test_counts_the_solved_points(self, tmp_path) -> None:
        write_stream(tmp_path, 3)
        found = scan_devsim_progress(tmp_path, total=10)
        assert found.done == 3
        assert found.total == 10

    def test_reports_the_last_bias_point(self, tmp_path) -> None:
        write_stream(tmp_path, 3)
        assert scan_devsim_progress(tmp_path, total=10).latest == "1V 풀림"

    def test_no_stream_yet_means_nothing_solved(self, tmp_path) -> None:
        found = scan_devsim_progress(tmp_path, total=10)
        assert found.done == 0
        assert found.latest is None

    def test_unknown_total_gives_nothing(self, tmp_path) -> None:
        # 0/0 을 그대로 보여주면 화면이 거짓말을 한다.
        assert scan_devsim_progress(tmp_path, total=0) is None

    def test_a_half_written_line_is_not_counted(self, tmp_path) -> None:
        """해석기가 줄을 쓰는 중에 읽을 수 있다. 깨진 줄을 세면 안 된다."""
        write_stream(tmp_path, 2)
        with (tmp_path / "iv.jsonl").open("a") as stream:
            stream.write('{"sweep": 1.5, "ste')
        assert scan_devsim_progress(tmp_path, total=10).done == 2

    def test_missing_directory_is_not_a_crash(self, tmp_path) -> None:
        assert scan_devsim_progress(tmp_path / "gone", total=10) is None


class TestPruneKeepsDevsimResults:
    def test_default_still_keeps_only_structures(self, tmp_path) -> None:
        (tmp_path / "a.str").write_text("x")
        (tmp_path / "job.in").write_text("y")
        prune_workdir(tmp_path)
        assert [p.name for p in tmp_path.iterdir()] == ["a.str"]

    def test_devsim_run_keeps_its_results(self, tmp_path) -> None:
        (tmp_path / "iv.json").write_text("{}")
        (tmp_path / "iv.jsonl").write_text("{}\n")
        (tmp_path / "device.json").write_text("{}")
        (tmp_path / "structure.str").write_text("x")
        (tmp_path / "remeshed.str").write_text("x")
        prune_workdir(tmp_path, keep=frozenset(), keep_names=DEVSIM_ARTIFACTS)
        left = sorted(p.name for p in tmp_path.iterdir())
        assert "iv.json" in left
        assert "iv.jsonl" in left

    def test_devsim_run_drops_the_bulky_inputs(self, tmp_path) -> None:
        """구조 파일은 결과보다 열 배 크고, 원본 잡에 그대로 남아 있다."""
        (tmp_path / "iv.json").write_text("{}")
        (tmp_path / "structure.str").write_text("x" * 1000)
        (tmp_path / "remeshed.str").write_text("x" * 5000)
        (tmp_path / "device.json").write_text("x" * 5000)
        freed = prune_workdir(tmp_path, keep=frozenset(), keep_names=DEVSIM_ARTIFACTS)
        left = sorted(p.name for p in tmp_path.iterdir())
        assert left == ["iv.json"]
        assert freed == 11000


class TestMovingBetweenCurves:
    """곡선 사이를 옮기는 동안에도 화면이 살아 있어야 한다.

    단계 하나를 옮기는 데 실측 solve 4회가 든다. 그동안 아무 줄도 안 나가면
    진행률이 멈춰 서서, 사용자는 해석이 죽은 줄 안다.

    다만 **푼 점으로 세면 안 된다.** 옮기는 것은 바이어스 점이 아니다 —
    세면 분자가 분모를 넘는다.
    """

    def write(self, workdir: Path, lines: list[str]) -> None:
        (workdir / "iv.jsonl").write_text("\n".join(lines) + "\n")

    def moving(self, vg: float) -> str:
        return json.dumps({"phase": "moving", "steps": {"Vg": vg}})

    def solved(self, vd: float) -> str:
        return json.dumps(
            {"sweep": vd, "steps": {"Vg": 1.0}, "currents": {"Vd": 1e-6}, "ok": True}
        )

    def test_moving_does_not_count_as_a_solved_point(self, tmp_path) -> None:
        self.write(tmp_path, [self.moving(1.0), self.solved(0.0)])
        found = scan_devsim_progress(tmp_path, total=10)
        assert found.done == 1

    def test_says_what_it_is_doing(self, tmp_path) -> None:
        self.write(tmp_path, [self.solved(0.0), self.moving(2.0)])
        assert "옮기는 중" in scan_devsim_progress(tmp_path, total=10).latest

    def test_names_the_step_it_is_moving_to(self, tmp_path) -> None:
        self.write(tmp_path, [self.moving(2.0)])
        assert "Vg=2V" in scan_devsim_progress(tmp_path, total=10).latest

    def test_a_solved_point_takes_the_message_back(self, tmp_path) -> None:
        self.write(tmp_path, [self.moving(1.0), self.solved(0.5)])
        latest = scan_devsim_progress(tmp_path, total=10).latest
        assert latest == "Vg=1V, 0.5V 풀림"

    def test_only_moving_so_far_means_nothing_solved(self, tmp_path) -> None:
        self.write(tmp_path, [self.moving(0.0)])
        assert scan_devsim_progress(tmp_path, total=10).done == 0

    def test_a_marker_without_steps_is_still_not_counted(self, tmp_path) -> None:
        # 단계 전압원이 없으면 조합이 비어 있다. 해석기는 그때 표시를 내보내지
        # 않지만, 옛 잡의 기록을 읽을 수도 있으니 세지는 않는다.
        self.write(tmp_path, [json.dumps({"phase": "moving", "steps": {}})])
        assert scan_devsim_progress(tmp_path, total=5).done == 0
