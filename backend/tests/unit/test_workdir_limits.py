"""잡 작업 디렉토리 크기 제한.

컨테이너에 붙는 /work 는 호스트 파일시스템 bind mount 다. 실제로 확인했다:
잡 하나가 몇 초 만에 호스트 디스크에 200MB 를 썼고 아무도 막지 않았다.
타임아웃 600초 × NVMe 쓰기 속도면 여유 공간을 전부 채워, 이 홈서버에서 같이
도는 다른 서비스까지 함께 죽는다.

/tmp 는 이미 tmpfs 64m 로 묶여 있지만 /work 는 상한이 없었다.
"""

from __future__ import annotations

import pytest

from app.runner.workdir import (
    WorkdirTooLarge,
    directory_size,
    enforce_size_limit,
    prune_workdir,
)


def write(path, name: str, size: int) -> None:
    (path / name).write_bytes(b"\0" * size)


class TestMeasuring:
    def test_empty_directory_is_zero(self, tmp_path) -> None:
        assert directory_size(tmp_path) == 0

    def test_sums_files(self, tmp_path) -> None:
        write(tmp_path, "a", 100)
        write(tmp_path, "b", 250)

        assert directory_size(tmp_path) == 350

    def test_includes_subdirectories(self, tmp_path) -> None:
        """사용자 코드는 셸을 통해 하위 디렉토리를 만들 수 있다."""
        nested = tmp_path / "deep" / "deeper"
        nested.mkdir(parents=True)
        write(nested, "c", 500)

        assert directory_size(tmp_path) == 500

    def test_ignores_a_vanished_file(self, tmp_path) -> None:
        """세는 도중 파일이 사라져도 예외로 죽으면 안 된다."""
        write(tmp_path, "a", 10)
        missing = tmp_path / "gone"
        missing.symlink_to(tmp_path / "does-not-exist")

        assert directory_size(tmp_path) == 10

    def test_does_not_follow_symlinks_out(self, tmp_path) -> None:
        """바깥을 가리키는 심볼릭 링크를 따라가면 호스트 전체를 세게 된다."""
        outside = tmp_path.parent / "outside.bin"
        outside.write_bytes(b"\0" * 1000)
        (tmp_path / "link").symlink_to(outside)

        assert directory_size(tmp_path) == 0


class TestEnforcing:
    def test_under_the_limit_passes(self, tmp_path) -> None:
        write(tmp_path, "a", 100)

        enforce_size_limit(tmp_path, limit_bytes=1000)

    def test_over_the_limit_raises(self, tmp_path) -> None:
        write(tmp_path, "a", 2000)

        with pytest.raises(WorkdirTooLarge):
            enforce_size_limit(tmp_path, limit_bytes=1000)

    def test_message_names_the_limit(self, tmp_path) -> None:
        """사용자가 무엇을 줄여야 하는지 알아야 한다."""
        write(tmp_path, "a", 2000)

        with pytest.raises(WorkdirTooLarge, match="1"):
            enforce_size_limit(tmp_path, limit_bytes=1000)


class TestPruning:
    def test_keeps_structure_files(self, tmp_path) -> None:
        write(tmp_path, "result.str", 100)

        prune_workdir(tmp_path)

        assert (tmp_path / "result.str").exists()

    def test_removes_everything_else(self, tmp_path) -> None:
        """산출물이 아닌 것은 남길 이유가 없다. 사용자가 쓴 임의 파일까지
        보관하면 디스크가 계속 는다."""
        write(tmp_path, "filler.bin", 5000)
        write(tmp_path, "job.in", 50)

        prune_workdir(tmp_path)

        assert not (tmp_path / "filler.bin").exists()
        assert not (tmp_path / "job.in").exists()

    def test_removes_subdirectories(self, tmp_path) -> None:
        nested = tmp_path / "scratch"
        nested.mkdir()
        write(nested, "junk", 100)

        prune_workdir(tmp_path)

        assert not nested.exists()

    def test_reports_freed_bytes(self, tmp_path) -> None:
        write(tmp_path, "filler.bin", 5000)
        write(tmp_path, "keep.str", 100)

        assert prune_workdir(tmp_path) == 5000

    def test_leaves_a_clean_directory_alone(self, tmp_path) -> None:
        write(tmp_path, "a.str", 10)
        write(tmp_path, "b.str", 20)

        assert prune_workdir(tmp_path) == 0
        assert directory_size(tmp_path) == 30
