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
