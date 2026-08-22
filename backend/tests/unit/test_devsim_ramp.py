"""전압을 목표까지 걸어 올리는 방식.

컨테이너 안에서 도는 `docker/devsim/run.py` 의 `Solver.ramp_to` 를 본다.
devsim 패키지가 dev extra 로 깔려 있어 장치 없이 임포트만으로 시험할 수 있다.

**왜 이걸 시험하나.** 실측한 고장이 여기 있었다. CMOS 인버터 부하선을 뽑는데
38 점 중 27 점이 수렴 실패로 버려졌다. 그런데 진짜로 어려운 점은 하나뿐이고
나머지는 전부 그 하나의 메아리였다 — 한 걸음이 실패하면 다음 점이 같은 자리에서
출발해 같은 첫 걸음을 다시 밟으므로, 반드시 같은 곳에서 또 실패한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "docker" / "devsim"))

import run  # noqa: E402


class FakeSolver(run.Solver):
    """장치 없이 도는 Solver. `solve` 가 언제 실패할지 시험이 정한다."""

    def __init__(self, fails):
        self.payload = {}
        self.relaxed = 0
        self.groups = {"V": ["c"]}
        self.applied = {"V": 0.0}
        self.pending = 0.0
        self.attempts: list[float] = []
        self._fails = fails

    def _set(self, bias, value):
        self.pending = value

    def solve(self):
        self.attempts.append(self.pending)
        if self._fails(self.pending):
            raise RuntimeError("Convergence failure!")


def hard_above(threshold: float, tolerance: float):
    """`threshold` 를 넘는 전압은 걸음이 `tolerance` 보다 크면 못 푼다.

    실제 소자가 이렇게 행동한다. 어려운 구간은 더 잘게 걸으면 넘어간다.
    """
    last = {"v": 0.0}

    def fails(value: float) -> bool:
        step = abs(value - last["v"])
        if value > threshold and step > tolerance + 1e-12:
            return True
        last["v"] = value
        return False

    return fails


class TestBisection:
    def test_halves_the_step_instead_of_giving_up(self) -> None:
        # 0.25 로는 못 넘지만 0.125 면 넘어가는 벽. 예전에는 여기서 포기했다.
        solver = FakeSolver(hard_above(1.25, 0.13))

        solver.ramp_to("V", 2.0)

        assert solver.applied["V"] == pytest.approx(2.0)

    def test_actually_used_a_smaller_step(self) -> None:
        solver = FakeSolver(hard_above(1.25, 0.13))

        solver.ramp_to("V", 2.0)

        gaps = [
            abs(b - a)
            for a, b in zip(solver.attempts, solver.attempts[1:])
            if b > a
        ]
        assert min(gaps) < run.MAX_BIAS_STEP

    def test_easy_ramp_still_walks_in_full_steps(self) -> None:
        """쉬운 구간까지 잘게 걸으면 느려진다. 실패했을 때만 줄여야 한다."""
        solver = FakeSolver(lambda value: False)

        solver.ramp_to("V", 1.0)

        assert len(solver.attempts) == 4  # 0.25 씩 네 걸음

    def test_gives_up_when_even_tiny_steps_fail(self) -> None:
        """진짜로 못 푸는 벽에서는 멈춰야 한다. 무한히 쪼개면 영영 안 끝난다."""
        solver = FakeSolver(lambda value: value > 1.25)

        with pytest.raises(Exception):
            solver.ramp_to("V", 2.0)

    def test_restores_the_bias_it_was_given(self) -> None:
        solver = FakeSolver(lambda value: value > 1.25)
        solver.applied["V"] = 0.5
        solver.pending = 0.5

        with pytest.raises(Exception):
            solver.ramp_to("V", 2.0)

        assert solver.applied["V"] == pytest.approx(0.5)
        assert solver.pending == pytest.approx(0.5)

    def test_keeps_the_ground_it_gained(self) -> None:
        """벽에 부딪혀도 거기까지 간 것은 세어 준다.

        다음 점이 0 에서 다시 걸어 올라오면 같은 길을 또 푼다.
        """
        solver = FakeSolver(lambda value: value > 1.25)

        assert solver.reached("V", 2.0) == pytest.approx(1.25, abs=0.13)


class TestFailureDoesNotCascade:
    def test_a_later_point_is_not_doomed_by_an_earlier_one(self) -> None:
        """한 점이 실패해도 다음 점은 스스로 판단할 기회를 얻어야 한다.

        실측: Vg=0 곡선에서 1.50 V 가 실패한 뒤 1.75, 2.00 … 5.00 이 전부
        실패했다. 모두 1.25 V 에서 출발해 같은 첫 걸음을 다시 밟았기 때문이다.
        """
        solver = FakeSolver(hard_above(1.25, 0.13))

        solver.ramp_to("V", 1.5)
        first = solver.applied["V"]
        solver.ramp_to("V", 1.75)

        assert first == pytest.approx(1.5)
        assert solver.applied["V"] == pytest.approx(1.75)


class TestRelaxedRetry:
    """엄격한 기준으로 안 풀리면 한 번만 느슨하게 다시 본다.

    실측: CMOS 인버터 부하선의 벽에서 뉴턴이 한계 순환에 빠졌다. RelError 가
    4.4e-3 과 3.8e-5 사이를 오갈 뿐 1e-5 아래로 내려가지 못했는데, 그동안
    AbsError 는 2.5e4 였다 — 실제로 전류가 흐를 때의 1e16~1e18 과 견주면
    사실상 0 이다. 답은 이미 정확한데 상대 기준만 못 넘고 있었다.
    """

    def test_relaxed_criterion_is_looser_than_the_strict_one(self) -> None:
        assert (
            run._TRANSPORT_RELAXED["relative_error"]
            > run._TRANSPORT["relative_error"]
        )

    def test_it_gets_more_iterations_too(self) -> None:
        # 느슨하게 보되 더 오래 본다. 한 번 더 봐서 될 일이면 그게 싸다.
        assert (
            run._TRANSPORT_RELAXED["maximum_iterations"]
            >= run._TRANSPORT["maximum_iterations"]
        )

    def test_a_rescued_solve_is_counted(self, monkeypatch) -> None:
        """몇 점이 구제됐는지 세어야 결과의 품질을 말할 수 있다."""
        calls = []

        def fake_solve(**kwargs):
            calls.append(kwargs["relative_error"])
            if kwargs["relative_error"] == run._TRANSPORT["relative_error"]:
                raise RuntimeError("Convergence failure!")

        monkeypatch.setattr(run.ds, "solve", fake_solve)
        solver = FakeSolver(lambda value: False)
        run.Solver.solve(solver)

        assert solver.relaxed == 1
        assert calls == [
            run._TRANSPORT["relative_error"],
            run._TRANSPORT_RELAXED["relative_error"],
        ]

    def test_an_easy_solve_never_relaxes(self, monkeypatch) -> None:
        monkeypatch.setattr(run.ds, "solve", lambda **kwargs: None)
        solver = FakeSolver(lambda value: False)

        run.Solver.solve(solver)

        assert solver.relaxed == 0

    def test_a_hopeless_point_still_raises(self, monkeypatch) -> None:
        """느슨하게 봐도 안 되면 실패는 실패다. 조용히 삼키면 안 된다."""
        def always_fails(**kwargs):
            raise RuntimeError("Convergence failure!")

        monkeypatch.setattr(run.ds, "solve", always_fails)
        solver = FakeSolver(lambda value: False)

        with pytest.raises(Exception):
            run.Solver.solve(solver)
