"""시뮬레이터에 넘기기 전 소스 다듬기.

**마지막 줄에 개행이 없으면 그 줄이 실행되지 않는다.** 실측으로 확인했다 —
CMOS 예제(160행)를 끝 개행 없이 돌리면:

    끝 개행 없음: "illegal input", 산출물 14개, 실패
    끝 개행 있음: 오류 없음,      산출물 15개, 성공

마지막 `structure out=ild.str` 이 실행되지 않아 산출물이 하나 사라지고, 이어서
러너가 보내는 `quit` 이 미완성 줄에 붙어 "illegal input" 이 난다.

브라우저 편집기에서 마지막 줄 끝에 Enter 를 치지 않는 것은 아주 흔하다. 사용자
탓으로 둘 수 없어 넘기기 전에 맞춰 준다.
"""

from __future__ import annotations

import pytest

from app.runner.runner import normalise_source


class TestTrailingNewline:
    def test_adds_a_missing_newline(self) -> None:
        assert normalise_source("structure out=a.str") == "structure out=a.str\n"

    def test_keeps_an_existing_one(self) -> None:
        assert normalise_source("init\n") == "init\n"

    def test_does_not_pile_up_newlines(self) -> None:
        """여러 번 저장해도 파일 끝이 계속 늘어나면 안 된다."""
        assert normalise_source("init\n\n\n") == "init\n\n\n"

    def test_empty_source_stays_empty(self) -> None:
        # 빈 소스에 개행만 넣어 봐야 의미가 없다.
        assert normalise_source("") == ""

    def test_whitespace_only_gets_a_newline(self) -> None:
        assert normalise_source("   ").endswith("\n")


class TestLineEndings:
    def test_converts_crlf(self) -> None:
        """레포의 예제 파일들이 CRLF 다. 붙여 넣으면 그대로 들어온다."""
        assert normalise_source("init\r\nstructure\r\n") == "init\nstructure\n"

    def test_converts_lone_cr(self) -> None:
        assert normalise_source("init\rstructure\r") == "init\nstructure\n"

    def test_leaves_lf_alone(self) -> None:
        assert normalise_source("init\nstructure\n") == "init\nstructure\n"


class TestRunnerUsesIt:
    def test_written_file_ends_with_a_newline(self, tmp_path) -> None:
        """러너가 job.in 을 쓸 때 적용되어야 의미가 있다."""
        from app.runner.sandbox import SOURCE_FILENAME
        from app.runner.runner import _write_source

        _write_source(tmp_path, "structure out=a.str")

        assert (tmp_path / SOURCE_FILENAME).read_text().endswith("\n")

    @pytest.mark.parametrize("source", ["a", "a\r\n", "a\n"])
    def test_always_ends_with_exactly_a_newline(self, source) -> None:
        assert normalise_source(source).endswith("\n")
