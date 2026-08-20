"""실행 중 공정 진행 계산.

로그는 실행이 끝나야 DB 에 들어오므로(stdout 을 한 번에 모아 기록한다), 도는
동안 "어디까지 갔는가"를 알려면 다른 단서가 필요하다. 작업디렉토리에 떨어진
`.str` 이 그것이다.
"""

from __future__ import annotations

from app.jobs.progress import Progress, scan_progress

SOURCE = """\
init boron conc=1e15
structure outfile = a.str
diffuse time=30 temp=1000
structure out=oxidation.str
etch oxide all
structure outf=c.str
"""


def touch(workdir, *names: str) -> None:
    for name in names:
        (workdir / name).write_text("dummy")


class TestCounting:
    def test_no_files_yet(self, tmp_path) -> None:
        assert scan_progress(tmp_path, SOURCE) == Progress(
            done=0, total=3, latest=None
        )

    def test_reports_the_last_completed_step(self, tmp_path) -> None:
        touch(tmp_path, "a.str", "oxidation.str")
        assert scan_progress(tmp_path, SOURCE) == Progress(
            done=2, total=3, latest="oxidation.str"
        )

    def test_all_done(self, tmp_path) -> None:
        touch(tmp_path, "a.str", "oxidation.str", "c.str")
        assert scan_progress(tmp_path, SOURCE) == Progress(
            done=3, total=3, latest="c.str"
        )

    def test_order_follows_the_source_not_the_filesystem(self, tmp_path) -> None:
        """파일 이름순이 아니라 소스에 적힌 순서가 공정 순서다."""
        touch(tmp_path, "c.str")
        assert scan_progress(tmp_path, SOURCE) == Progress(
            done=3, total=3, latest="c.str"
        )

    def test_ignores_files_the_source_never_asked_for(self, tmp_path) -> None:
        touch(tmp_path, "a.str", "stray.str")
        assert scan_progress(tmp_path, SOURCE) == Progress(
            done=1, total=3, latest="a.str"
        )


class TestDegenerateSources:
    def test_no_structure_command_means_nothing_to_report(self, tmp_path) -> None:
        """진행을 셀 근거가 없으면 0/0 을 지어내지 않는다."""
        assert scan_progress(tmp_path, "init boron conc=1e15\n") is None

    def test_same_name_written_twice_counts_once(self, tmp_path) -> None:
        """덮어쓰는 파일은 단계가 둘이어도 셀 수 있는 것은 하나뿐이다.

        두 번 세면 파일 하나가 생긴 순간 진행이 두 칸 뛴다.
        """
        source = "structure out=r.str\ndiffuse time=10\nstructure out=r.str\n"
        assert scan_progress(tmp_path, source) == Progress(
            done=0, total=1, latest=None
        )

    def test_missing_workdir_is_not_an_error(self, tmp_path) -> None:
        """청소된 잡을 조회해도 500 이 나면 안 된다."""
        assert scan_progress(tmp_path / "gone", SOURCE) is None

    def test_paths_in_the_source_are_reduced_to_names(self, tmp_path) -> None:
        touch(tmp_path, "deep.str")
        source = "structure out=./sub/deep.str\n"
        assert scan_progress(tmp_path, source) == Progress(
            done=1, total=1, latest="deep.str"
        )
