"""실행 로그의 상한과 전문 보관.

상한 자체는 필요하다 — 시뮬레이터는 인식하지 못한 첫 단어를 `/bin/bash` 로
넘기므로 사용자가 무한 출력을 낼 수 있고, 그대로 DB 에 넣으면 한 행이
기가바이트가 된다. 문제는 상한이 **평범한 실행까지 잘랐다는 것**이다. 실측:
41 단계 공정 흐름 한 건이 224,708 자, 번들 CMOS 예제가 182,425 자인데 상한이
200,000 자였다.

그래서 두 가지를 나눈다. DB 에는 넉넉하지만 유한한 미리보기를 넣고, 전문은
잡 작업디렉토리에 파일로 남겨 언제든 내려받게 한다.
"""

from __future__ import annotations

from pathlib import Path

from app.runner.logfile import (
    FULL_LOG_NAME,
    full_log_path,
    read_full_log,
    write_full_log,
)
from app.runner.runner import (
    LOG_TRUNCATION_NOTICE,
    _MAX_LOG_CHARS,
    _truncate_log,
    was_truncated,
)

#: 실측한 41 단계 공정 흐름의 로그 크기. 이보다 짧은 상한은 평범한 실행을
#: 자른다.
REAL_FLOW_CHARS = 224_708


class TestTruncationThreshold:
    def test_a_real_run_is_not_truncated(self) -> None:
        """실제로 돌린 공정 흐름 한 건은 손대지 않아야 한다."""
        log = "x" * REAL_FLOW_CHARS

        assert _truncate_log(log) == log

    def test_headroom_over_a_real_run(self) -> None:
        """상한은 실측치보다 넉넉해야 한다. 딱 맞추면 다음 실행에서 또 잘린다."""
        assert _MAX_LOG_CHARS >= 4 * REAL_FLOW_CHARS

    def test_runaway_output_is_still_capped(self) -> None:
        """상한을 없애는 것이 아니다. DB 한 행은 여전히 유한해야 한다."""
        log = "y" * (_MAX_LOG_CHARS * 3)

        trimmed = _truncate_log(log)

        assert len(trimmed) < _MAX_LOG_CHARS + len(LOG_TRUNCATION_NOTICE) + 200


class TestTruncationShape:
    def test_keeps_both_ends(self) -> None:
        """오류는 보통 끝에 나오지만 무엇을 하다 그랬는지는 앞에 있다."""
        log = "머리" + "z" * (_MAX_LOG_CHARS * 2) + "꼬리"

        trimmed = _truncate_log(log)

        assert trimmed.startswith("머리")
        assert trimmed.endswith("꼬리")

    def test_says_it_was_truncated(self) -> None:
        """말없이 자르면 사용자는 로그가 그게 전부인 줄 안다."""
        trimmed = _truncate_log("q" * (_MAX_LOG_CHARS * 2))

        assert LOG_TRUNCATION_NOTICE in trimmed


class TestWasTruncated:
    def test_detects_a_truncated_log(self) -> None:
        assert was_truncated(_truncate_log("w" * (_MAX_LOG_CHARS * 2)))

    def test_short_log_is_not_flagged(self) -> None:
        assert not was_truncated(_truncate_log("짧은 로그"))

    def test_none_is_not_flagged(self) -> None:
        """아직 실행 전이라 로그가 없는 잡도 있다."""
        assert not was_truncated(None)


class TestFullLogFile:
    def test_round_trip(self, tmp_path: Path) -> None:
        log = "한글과 ascii 가 섞인 로그\n" * 5000

        write_full_log(tmp_path, log)

        assert read_full_log(tmp_path) == log

    def test_written_where_the_reader_looks(self, tmp_path: Path) -> None:
        write_full_log(tmp_path, "내용")

        assert full_log_path(tmp_path) == tmp_path / FULL_LOG_NAME
        assert full_log_path(tmp_path).read_text(encoding="utf-8") == "내용"

    def test_missing_file_reads_as_none(self, tmp_path: Path) -> None:
        """산출물이 정리되면 작업디렉토리째 사라진다. 터지면 안 된다."""
        assert read_full_log(tmp_path) is None

    def test_missing_workdir_reads_as_none(self, tmp_path: Path) -> None:
        assert read_full_log(tmp_path / "사라진-잡") is None

    def test_write_survives_a_missing_workdir(self, tmp_path: Path) -> None:
        """로그를 못 남긴다고 잡 전체를 실패시키면 안 된다."""
        assert write_full_log(tmp_path / "없는곳", "내용") is None
