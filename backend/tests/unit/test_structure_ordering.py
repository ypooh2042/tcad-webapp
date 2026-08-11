"""산출물 순서 결정 테스트.

순서는 소스의 `structure out=` 등장 순서를 따른다. 파일시스템 타임스탬프는
쓸 수 없다 — 리눅스가 inode 시각을 타이머 틱 단위로 주기 때문에 짧은
시뮬레이션에서 여러 파일이 `st_mtime_ns` 까지 동일한 값을 받는다.
"""

from pathlib import Path

import pytest

from app.runner.results import collect_structure_files

#: 레포 루트 기준으로 찾는다. 절대 경로를 박으면 다른 환경에서 못 돌고
#: 레포에 개인 경로가 남는다.
REPO_ROOT = Path(__file__).resolve().parents[3]
SUPREM_EXAMPLES = REPO_ROOT / "SUPREM4GS" / "examples"


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    return tmp_path


def touch(workdir: Path, *names: str) -> None:
    for name in names:
        (workdir / name).write_text("v X\n")


class TestSourceOrder:
    def test_follows_source_not_filename(self, workdir) -> None:
        touch(workdir, "zzz_first.str", "aaa_second.str")
        source = "structure out=zzz_first.str\nstructure out=aaa_second.str\n"

        assert [p.name for p in collect_structure_files(workdir, source)] == [
            "zzz_first.str",
            "aaa_second.str",
        ]

    def test_handles_many_steps(self, workdir) -> None:
        names = [f"step{i}.str" for i in range(10)]
        touch(workdir, *names)
        source = "".join(f"structure out={n}\n" for n in reversed(names))

        assert [p.name for p in collect_structure_files(workdir, source)] == list(
            reversed(names)
        )


class TestPrefixAbbreviation:
    """SUPREM 은 커맨드와 파라미터를 고유 접두사로 해석한다."""

    @pytest.mark.parametrize(
        "line",
        [
            "structure out=a.str",
            "structure outfile=a.str",
            "struct out=a.str",
            "stru out=a.str",
            "structure  out = a.str",
            "  structure out=a.str",
        ],
    )
    def test_recognises_abbreviated_forms(self, workdir, line: str) -> None:
        touch(workdir, "a.str")
        assert [p.name for p in collect_structure_files(workdir, line)] == ["a.str"]

    def test_ignores_stress_card(self, workdir) -> None:
        """`str` 까지는 stress 와 겹친다. stress 를 구조 저장으로 오인하면 안 된다."""
        touch(workdir, "a.str")
        source = "stress out=a.str\n"

        assert collect_structure_files(workdir, source)[0].name == "a.str"
        # 소스 순서로는 못 찾았지만 산출물은 유실되지 않아야 한다.
        assert len(collect_structure_files(workdir, source)) == 1

    def test_structure_infile_is_not_an_output(self, workdir) -> None:
        """`structure infile=` 은 읽기다. 쓰기로 세면 순서가 어긋난다."""
        touch(workdir, "written.str")
        source = "structure infile=read.str\nstructure out=written.str\n"

        assert [p.name for p in collect_structure_files(workdir, source)] == [
            "written.str"
        ]


class TestUnlistedFiles:
    def test_files_not_in_source_are_kept(self, workdir) -> None:
        """산출물 유실은 순서 오류보다 나쁘다."""
        touch(workdir, "declared.str", "surprise.str")
        source = "structure out=declared.str\n"

        assert [p.name for p in collect_structure_files(workdir, source)] == [
            "declared.str",
            "surprise.str",
        ]

    def test_missing_file_is_skipped_not_faked(self, workdir) -> None:
        """소스가 언급했어도 실제로 안 만들어졌으면 빼야 한다."""
        touch(workdir, "made.str")
        source = "structure out=made.str\nstructure out=never_made.str\n"

        assert [p.name for p in collect_structure_files(workdir, source)] == [
            "made.str"
        ]

    def test_empty_source_still_returns_files(self, workdir) -> None:
        touch(workdir, "b.str", "a.str")
        assert [p.name for p in collect_structure_files(workdir, "")] == [
            "a.str",
            "b.str",
        ]


class TestRealExample:
    def test_cmos_example_order_matches_process_flow(self, workdir) -> None:
        """실제 CMOS 공정 흐름 15단계로 확인한다."""
        cmos = SUPREM_EXAMPLES / "mosfet" / "CMOS.in"
        if not cmos.exists():
            pytest.skip("CMOS.in 예제를 찾을 수 없습니다")
        source = cmos.read_text()

        expected = [
            "substrate.str",
            "oxidation.str",
            "nitride.str",
            "nitride_etch.str",
            "field_oxide.str",
            "nitride_remove.str",
            "vth_implant.str",
            "oxide_etch.str",
            "gate_oxide.str",
            "poly_gate.str",
            "poly_etch.str",
            "ldd.str",
            "sidewall.str",
            "source.str",
            "ild.str",
        ]
        touch(workdir, *expected)

        assert [p.name for p in collect_structure_files(workdir, source)] == expected
