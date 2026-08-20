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
        assert scan_devsim_progress(tmp_path, total=10).latest == "1V"

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
