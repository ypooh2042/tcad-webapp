"""로그에서 실패를 알아내기.

종료 코드는 쓸 수 없다. SUPREM4GS 는 커맨드 오류가 있어도 exit 0 으로 끝난다.
그래서 로그 문구로 판정하는데, **놓친 문구가 있으면 아무것도 만들지 못한 실행이
"성공"으로 기록된다.** 실제로 그런 일이 있었다:

    no value specified for ylo
    user mesh data not given or incomplete
    No mesh defined!
    → 상태 SUCCEEDED, 산출물 3개, 전부 노드 0개

사용자에게는 빈 그래프만 보이고 왜 그런지 알 방법이 없었다.

문구는 suprem 바이너리의 문자열 테이블에서 확인했다(`strings -n 6 suprem`).
"""

from __future__ import annotations

import pytest

from app.runner.results import describe_abnormal_exit, SimulationResult, extract_errors

BANNER = (
    "SUPREM-IV.GS B.9305\n"
    "\t(c) 1991-1993 Stanford University\n"
    "Reading Models...\n"
)


def result(log: str, exit_code: int = 0) -> SimulationResult:
    return SimulationResult(
        exit_code=exit_code,
        log=log,
        timed_out=False,
        structure_files=(),
        errors=extract_errors(log),
    )


class TestMeshFailures:
    """메시를 못 만들면 그 뒤 모든 커맨드가 빈 구조를 쓴다."""

    @pytest.mark.parametrize(
        "line",
        [
            "No mesh defined!",
            "user mesh data not given or incomplete",
            "no value specified for ylo",
            "No material specified for region 2",
            "no region yet",
            "no orientation given",
        ],
    )
    def test_is_detected(self, line) -> None:
        assert extract_errors(f"{BANNER}{line}\n") == (line,)

    def test_run_is_not_successful(self) -> None:
        assert not result(f"{BANNER}No mesh defined!\n").succeeded


class TestCommandFailures:
    @pytest.mark.parametrize(
        "line",
        [
            "errors detected on command input",
            "the command is ambiguous",
            "ambiguous parameter - backside",
            "illegal input",
            "no command defined for name zzz",
            "no such x tag: top",
            "bad expression: 1 +",
            "no character string given for outfile",
        ],
    )
    def test_is_detected(self, line) -> None:
        assert extract_errors(f"{BANNER}{line}\n") == (line,)


class TestNoFalsePositives:
    def test_the_success_message_is_not_an_error(self) -> None:
        """`no error in %s command input` 은 성공 메시지다.

        `^no ` 처럼 넓게 잡으면 정상 실행이 실패로 뒤집힌다.
        """
        assert extract_errors(f"{BANNER}no error in diffuse command input\n") == ()

    def test_banner_alone_is_clean(self) -> None:
        assert extract_errors(BANNER) == ()

    def test_normal_output_is_clean(self) -> None:
        log = (
            f"{BANNER}"
            "Mesh statistics Mesh Creation:\n"
            "    Points =  121\tNodes =  121\t\n"
            "user 0.041667\n"
        )

        assert extract_errors(log) == ()

    def test_clean_run_succeeds(self) -> None:
        assert result(f"{BANNER}Points = 121\n").succeeded


class TestShellFallthrough:
    def test_command_not_found_is_an_error(self) -> None:
        """인식하지 못한 첫 단어는 /bin/bash 로 넘어간다. 조용히 지나가면
        오타가 그대로 통과한다."""
        log = f"{BANNER}/bin/bash: line 1: strcture: command not found\n"

        assert extract_errors(log)

    def test_localised_shell_message_is_caught(self) -> None:
        """bash 메시지는 로케일에 따라 번역된다. 영어 문구만 찾으면 한국어
        환경에서 셸 fall-through 를 통째로 놓친다."""
        log = f"{BANNER}/bin/bash: 줄 1: strcture: 명령어를 찾을 수 없음\n"

        assert extract_errors(log)


class TestAbnormalTermination:
    """시뮬레이터가 신호로 죽었을 때.

    세그폴트가 나면 **로그가 통째로 비어 나온다** — 버퍼가 플러시되지 못하고
    사라지기 때문이다. 오류 줄이 없으니 화면에 아무 단서도 남지 않고, 사용자는
    왜 실패했는지 알 방법이 없다(exit_code=139, log='' 로 실측).
    """

    def test_names_the_signal(self) -> None:
        message = describe_abnormal_exit(139)

        assert message is not None
        assert "SIGSEGV" in message

    def test_points_at_the_grid_not_the_syntax(self) -> None:
        # 문법 오류로 오해하면 멀쩡한 입력을 붙들고 시간을 버린다.
        assert "격자" in describe_abnormal_exit(139)

    def test_says_nothing_for_a_normal_exit(self) -> None:
        assert describe_abnormal_exit(0) is None
        # 커맨드 오류는 로그가 설명한다. 여기서 덧붙이면 잡음이다.
        assert describe_abnormal_exit(1) is None

    def test_covers_other_signals(self) -> None:
        assert "SIGABRT" in describe_abnormal_exit(134)
        assert "SIGKILL" in describe_abnormal_exit(137)


class TestGridSizeIsReported:
    """격자가 컸다면 그 숫자를 알려 준다.

    예전에는 "영역당 약 10,900 점이 한계"라고 안내했다. 그 한계는 geom.h 의
    16 비트 카운터 때문이었고 patch 0009 로 걷어냈다 — 실측으로 예전에 죽던
    격자가 15,276 점으로 완주한다. 없는 한계를 근거로 조언하면 사용자가 멀쩡한
    격자를 붙들고 시간을 버리므로, 이제 **크기만 사실대로** 알린다.
    """

    LOG = "Mesh statistics Mesh Creation:\n    Points = 12236\tNodes = 12500\t\n"

    def test_names_the_grid_size(self) -> None:
        message = describe_abnormal_exit(139, self.LOG)

        assert "12,236" in message

    def test_does_not_claim_a_limit(self) -> None:
        message = describe_abnormal_exit(139, self.LOG)

        assert "한계" not in message, message

    def test_still_suggests_coarsening(self) -> None:
        # 크기를 알려만 주고 무엇을 해 볼지 말하지 않으면 쓸모가 없다.
        assert "성기게" in describe_abnormal_exit(139, self.LOG)

    def test_says_nothing_about_size_when_the_log_is_empty(self) -> None:
        message = describe_abnormal_exit(139, "")

        assert "격자가" not in message
        assert "SIGSEGV" in message

    def test_uses_the_last_mesh_size_in_the_log(self) -> None:
        # 공정이 진행되며 격자가 커진다. 죽은 시점의 크기가 알고 싶은 값이다.
        log = (
            "Mesh statistics Mesh Creation:\n    Points = 400\tNodes = 410\t\n"
            "Mesh statistics after deposit:\n    Points = 9000\tNodes = 9100\t\n"
        )

        assert "9,000" in describe_abnormal_exit(139, log)


class TestPanicNamesTheCommand:
    """panic 안내는 죽은 커맨드에 맞춰야 한다.

    같은 `not clock wise` 라도 `etch` 중에 죽는 것과 `diffuse` 중에 죽는 것은
    사용자가 할 일이 다르다. 실측한 사례: 41 단계 흐름이 step 20 의
    screen oxidation(`diffuse`) 안에서 죽었는데 안내는 `etch dry` 를 짚어,
    멀쩡한 식각 깊이를 붙들게 만들었다.

    로그는 입력을 되울리지 않지만 `Mesh statistics <단계>:` 를 남긴다
    (`dbase/geometry.c:63`, 출력 지점이 하나뿐이다). 그 마지막 표지가 어느
    커맨드였는지 알려 준다.
    """

    PANIC = "suprem4 panic: triangles are not clock wise, data base corrupted\n"

    def message(self, phase: str) -> str:
        return describe_abnormal_exit(
            139, f"Mesh statistics {phase}:\n    Points = 100\tNodes = 110\t\n" + self.PANIC
        )

    def test_diffusion_does_not_blame_etch(self) -> None:
        message = self.message("during update of diffusion")

        assert "etch dry" not in message
        assert "diffuse" in message

    def test_oxide_growth_phases_count_as_diffusion(self) -> None:
        # 산화 중 격자 갱신은 전부 diffuse 안에서 일어난다.
        for phase in (
            "Grid Addition",
            "after removing silicon nodes",
            "after native oxide deposit",
            "native oxide deposition",
        ):
            assert "diffuse" in self.message(phase), phase

    def test_etch_still_gets_the_etch_advice(self) -> None:
        for phase in ("after etch", "after etch cut"):
            message = self.message(phase)
            assert "etch" in message, phase
            assert "깎는 깊이" in message, phase

    def test_deposit_gets_its_own_advice(self) -> None:
        message = self.message("after deposit")

        assert "deposit" in message
        assert "깎는 깊이" not in message

    def test_falls_back_when_the_phase_is_unknown(self) -> None:
        """모르는 단계에서도 panic 문구 자체는 보여준다."""
        message = describe_abnormal_exit(139, self.PANIC)

        assert "not clock wise" in message

    def test_uses_the_phase_nearest_the_panic(self) -> None:
        """공정은 여러 단계를 지난다. 죽은 시점의 단계가 알고 싶은 값이다."""
        log = (
            "Mesh statistics after etch:\n"
            "Mesh statistics during update of diffusion:\n" + self.PANIC
        )

        assert "etch dry" not in describe_abnormal_exit(139, log)

    def test_ignores_markers_printed_after_the_panic(self) -> None:
        log = self.PANIC + "Mesh statistics after etch:\n"

        assert "etch dry" not in describe_abnormal_exit(139, log)
