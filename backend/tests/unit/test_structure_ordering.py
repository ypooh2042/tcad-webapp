"""산출물 순서 결정 테스트.

순서는 소스의 `structure out=` 등장 순서를 따른다. 파일시스템 타임스탬프는
쓸 수 없다 — 리눅스가 inode 시각을 타이머 틱 단위로 주기 때문에 짧은
시뮬레이션에서 여러 파일이 `st_mtime_ns` 까지 동일한 값을 받는다.
"""

from pathlib import Path

import pytest

from app.runner.results import STRUCTURE_OUT_RE, collect_structure_files

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
    def test_nmos_example_order_matches_process_flow(self, workdir) -> None:
        """실제 nMOS 공정 흐름 25단계로 확인한다.

        이 예제의 이름은 숫자 접두사를 쓰므로 **이름순과 공정순이 실제로
        다르다** — 이름순이면 1, 10, 11 … 19, 2, 20 … 이 되어 흐름이
        뒤집힌다. 소스 순서를 따르는지 보기에 이보다 나은 표본이 없다.
        """
        example = SUPREM_EXAMPLES / "mosfet" / "nmos.in"
        if not example.exists():
            pytest.skip("nmos.in 예제를 찾을 수 없습니다")
        source = example.read_text()

        expected = [
            "1_substrate.str",
            "2_oxidation.str",
            "3_nitride.str",
            "4_nitride_mask_litho.str",
            "5_nitride_etch.str",
            "6_pr_strip.str",
            "7_field_oxide.str",
            "8_nitride_remove.str",
            "9_pts_implant.str",
            "10_vth_implant.str",
            "11_oxide_etch.str",
            "12_gate_oxide.str",
            "13_poly_gate.str",
            "14_gate_litho.str",
            "15_gate_etch.str",
            "16_pr_strip.str",
            "17_ldd.str",
            "18_sidewall.str",
            "19_sd_implant.str",
            "20_ild.str",
            "21_planarization.str",
            "22_via_mask_litho.str",
            "23_via_etch.str",
            "24_pr_strip.str",
            "25_metal_contact.str",
        ]
        touch(workdir, *expected)

        assert [p.name for p in collect_structure_files(workdir, source)] == expected

    def test_name_order_would_get_it_wrong(self, workdir) -> None:
        """이름순 정렬이 실제로 다른 답을 낸다는 것을 못 박는다.

        표본이 이름순과 우연히 같으면 이 시험은 아무것도 지키지 못한다.
        """
        example = SUPREM_EXAMPLES / "mosfet" / "nmos.in"
        if not example.exists():
            pytest.skip("nmos.in 예제를 찾을 수 없습니다")

        names = [
            m.group(1) for m in STRUCTURE_OUT_RE.finditer(example.read_text())
        ]

        assert names != sorted(names)
