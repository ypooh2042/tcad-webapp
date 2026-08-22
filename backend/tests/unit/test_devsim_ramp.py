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
        # 카운터·상태는 진짜 Solver 것을 그대로 쓴다. 여기서 손으로 나열하면
        # `Solver` 에 속성이 하나 늘 때마다 이 픽스처가 깨진다 — 실제로 깨졌다.
        run.Solver._reset_counters(self)
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
            strict = kwargs["relative_error"] == run._TRANSPORT["relative_error"]
            return {"converged": not strict, "iterations": [{}]}

        monkeypatch.setattr(run.ds, "solve", fake_solve)
        solver = FakeSolver(lambda value: False)
        run.Solver.solve(solver)

        assert solver.relaxed == 1
        assert calls == [
            run._TRANSPORT["relative_error"],
            run._TRANSPORT_RELAXED["relative_error"],
        ]

    def test_an_easy_solve_never_relaxes(self, monkeypatch) -> None:
        monkeypatch.setattr(
            run.ds, "solve", lambda **kwargs: {"converged": True, "iterations": [{}]}
        )
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


class TestInfoSolveStillRaises:
    """`info=True` 는 **실패 계약을 바꾼다.** 이 시험이 그것을 못 박는다.

    실측 확인:

        info 없이 : 예외를 올린다   devsim.error("Convergence failure!")
        info=True : 예외 없이 반환   {"converged": False, "iterations": [...]}

    `Solver.solve`·`_try`·`ramp_to`·`reached` 는 전부 **예외로** 실패를 판정한다.
    `info=True` 를 그냥 끼우면 모든 수렴 실패가 조용히 성공으로 둔갑하고,
    발산한 값으로 전류를 읽어 **틀린 곡선을 정상 결과로 내보낸다.**
    계측을 넣는 일이 가장 무해해 보이지만, 조용히 틀릴 수 있는 자리는 여기뿐이다.
    """

    def _reply(self, converged: bool, iterations: int = 3):
        return {
            "converged": converged,
            "iterations": [
                {
                    "iteration": i,
                    "devices": [
                        {
                            "name": "device",
                            "absolute_error": 2.5e4,
                            "relative_error": 4.4e-3,
                            "regions": [
                                {
                                    "name": "r1_silicon",
                                    "equations": [
                                        {
                                            "name": "ElectronContinuityEquation",
                                            "absolute_error": 1.6e4,
                                            "relative_error": 4.4e-3,
                                            "absolute_error_node": 12345,
                                            "relative_error_node": 12345,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
                for i in range(iterations)
            ],
        }

    def test_not_converged_must_raise(self, monkeypatch) -> None:
        monkeypatch.setattr(
            run.ds, "solve", lambda **kw: self._reply(converged=False)
        )
        solver = FakeSolver(lambda v: False)

        with pytest.raises(Exception):
            run.Solver.solve(solver)

    def test_a_silent_failure_is_never_counted_as_a_rescue(self, monkeypatch) -> None:
        """둘 다 안 풀렸으면 구제된 것이 아니다. relaxed 가 올라가면 안 된다."""
        monkeypatch.setattr(
            run.ds, "solve", lambda **kw: self._reply(converged=False)
        )
        solver = FakeSolver(lambda v: False)

        with pytest.raises(Exception):
            run.Solver.solve(solver)

        assert solver.relaxed == 0

    def test_strict_fail_then_relaxed_success_counts_as_a_rescue(
        self, monkeypatch
    ) -> None:
        seen = []

        def fake(**kw):
            seen.append(kw["relative_error"])
            ok = kw["relative_error"] != run._TRANSPORT["relative_error"]
            return self._reply(converged=ok)

        monkeypatch.setattr(run.ds, "solve", fake)
        solver = FakeSolver(lambda v: False)

        run.Solver.solve(solver)

        assert solver.relaxed == 1
        assert seen == [
            run._TRANSPORT["relative_error"],
            run._TRANSPORT_RELAXED["relative_error"],
        ]

    def test_the_message_names_what_blocked_it(self, monkeypatch) -> None:
        """막힌 자리를 문구에 담는다 — 이 문구가 결과 파일의 `reason` 이 된다.

        지금은 어느 노드가 수렴을 막았는지 알려면 사람이 로그를 읽어야 한다.
        """
        monkeypatch.setattr(
            run.ds, "solve", lambda **kw: self._reply(converged=False)
        )
        solver = FakeSolver(lambda v: False)

        with pytest.raises(Exception) as caught:
            run.Solver.solve(solver)

        message = str(caught.value)
        assert "ElectronContinuityEquation" in message
        assert "12345" in message

    def test_a_real_devsim_exception_is_still_raised(self, monkeypatch) -> None:
        """특이 행렬 같은 진짜 예외는 여전히 그대로 올라와야 한다."""
        def explode(**kw):
            raise RuntimeError("Convergence failure!")

        monkeypatch.setattr(run.ds, "solve", explode)
        solver = FakeSolver(lambda v: False)

        with pytest.raises(Exception, match="Convergence failure"):
            run.Solver.solve(solver)

    def test_newton_iterations_are_counted(self, monkeypatch) -> None:
        monkeypatch.setattr(
            run.ds, "solve", lambda **kw: self._reply(converged=True, iterations=7)
        )
        solver = FakeSolver(lambda v: False)

        run.Solver.solve(solver)

        assert solver.newton == 7
        assert solver.solves == 1


class TestDevsimRollsBackItself:
    """실패한 solve 뒤에 노드 값을 **우리가** 되돌릴 필요는 없다.

    한때 "실패하면 뉴턴이 헤매다 만 값이 장치에 남아 다음 걸음이 거기서
    출발한다"고 보고 복원 코드를 넣었다. 벤치마크 결과가 비트 단위로 같았고,
    실제로 재 보니 **DevSim 이 스스로 되돌린다** — 강제로 실패시킨 뒤 노드 값
    변화가 정확히 0.000e+00 V 였다.

    이 시험은 그 사실을 붙들어 둔다. DevSim 이 이 성질을 잃으면 여기서 깨지고,
    그때는 복원 코드가 필요해진다.
    """

    def test_a_failed_solve_leaves_the_previous_solution(self) -> None:
        import devsim as ds

        ds.reset_devsim()
        ds.create_1d_mesh(mesh="m")
        ds.add_1d_mesh_line(mesh="m", pos=0, ps=1e-7, tag="l")
        ds.add_1d_mesh_line(mesh="m", pos=1e-4, ps=1e-7, tag="r")
        ds.add_1d_contact(mesh="m", name="c0", tag="l", material="metal")
        ds.add_1d_contact(mesh="m", name="c1", tag="r", material="metal")
        ds.add_1d_region(mesh="m", material="Si", region="r", tag1="l", tag2="r")
        ds.finalize_mesh(mesh="m")
        ds.create_device(mesh="m", device="d")

        from devsim.python_packages.simple_physics import (
            CreateSiliconPotentialOnly,
            CreateSiliconPotentialOnlyContact,
            CreateSolution,
            GetContactBiasName,
            SetSiliconParameters,
        )

        SetSiliconParameters("d", "r", 300)
        CreateSolution("d", "r", "Potential")
        ds.node_model(device="d", region="r", name="NetDoping", equation="1e18")
        CreateSiliconPotentialOnly("d", "r")
        for contact in ("c0", "c1"):
            ds.set_parameter(device="d", name=GetContactBiasName(contact), value=0.0)
            CreateSiliconPotentialOnlyContact("d", "r", contact)
        ds.solve(type="dc", absolute_error=1e-13, relative_error=1e-12,
                 maximum_iterations=30)

        before = list(ds.get_node_model_values(device="d", region="r", name="Potential"))
        # 못 풀 조건: 큰 바이어스에 반복 2회
        ds.set_parameter(device="d", name=GetContactBiasName("c0"), value=30.0)
        with pytest.raises(Exception):
            ds.solve(type="dc", absolute_error=1e-13, relative_error=1e-12,
                     maximum_iterations=2)

        after = list(ds.get_node_model_values(device="d", region="r", name="Potential"))
        assert after == before, "DevSim 이 더는 스스로 되돌리지 않는다 — 복원 코드가 필요하다"


class TestFloatingContactsInRunPy:
    """부유 전압원을 회로 노드로 만드는 자리.

    실측으로 확인한 지뢰 둘을 여기서 막는다.

    **1. `set_parameter` 가 회로 별칭을 덮어쓴다.** `run.py` 는 지금 모든
    접촉에 `set_parameter(GetContactBiasName(...))` 를 건다. 그 파라미터가
    존재하면 `circuit_node_alias` 가 무력화되고, 조용히 틀리는 것이 아니라
    **수렴 자체가 깨진다**(출력이 0 에 붙박이).

    **2. 전위만 푸는 평형 단계에서는 회로 노드 행이 빈다.**
    `CreateSiliconPotentialOnlyContact(is_circuit=True)` 가 만드는 접촉
    방정식에는 전하만 있고 전류 모델이 없어서(`simple_physics.py:229-241`),
    평형 단계에서는 전류가 노드로 안 들어가 행렬이 특이해진다. 그래서 접지로
    가는 아주 큰 저항을 상시 매단다 — 1e12 Ω 이면 5 V 에서 5 pA 라 µA 대
    전류에 영향이 없다.
    """

    def test_the_source_skips_set_parameter_for_floating_contacts(self) -> None:
        source = (
            Path(__file__).resolve().parents[3] / "docker" / "devsim" / "run.py"
        ).read_text()
        # set_parameter 를 거는 자리 **바로 앞**에 부유 여부를 가르는 분기가
        # 있어야 한다. 앞뒤 20 줄 안에서 찾는다.
        lines = source.splitlines()
        at = next(
            i for i, line in enumerate(lines)
            if "GetContactBiasName(contact[" in line and "set_parameter" in
            "".join(lines[max(0, i - 3): i + 1])
        )
        around = "\n".join(lines[max(0, at - 20): at + 1])

        assert "is_floating" in around, (
            "부유 접촉에 set_parameter 를 걸면 회로 별칭이 무력화되어 "
            f"수렴이 깨진다 — 반드시 건너뛰어야 한다. 본 자리:\n{around}"
        )

    def test_a_shunt_resistor_is_attached(self) -> None:
        source = (
            Path(__file__).resolve().parents[3] / "docker" / "devsim" / "run.py"
        ).read_text()

        assert "circuit_element" in source, "부유 노드에 접지 경로가 필요하다"
        assert "SHUNT_OHMS" in source

    def test_the_shunt_is_large_enough_to_ignore(self) -> None:
        import importlib

        module = importlib.import_module("run")
        importlib.reload(module)
        # 5 V 에서 흐르는 전류가 µA 대 신호의 100 만분의 1 아래여야 한다.
        leak_amps = 5.0 / module.SHUNT_OHMS
        assert leak_amps < 1e-9, f"{leak_amps:.1e} A 는 무시할 수 없다"


class TestSolverLeavesFloatingAlone:
    """부유 전압원은 **걸어 주는** 대상이 아니다.

    `_set` 은 `ds.set_parameter` 를 부른다. 부유 접촉에 그걸 걸면 회로 별칭이
    무력화되어 수렴이 깨진다 — 접촉을 만들 때만이 아니라 스윕 도중에도
    마찬가지다. 그래서 `Solver` 가 아예 그 전압원을 모르게 한다.
    """

    def payload(self):
        return {
            "contacts": [
                {"name": "c1", "bias": "Vin", "region": "r"},
                {"name": "c2", "bias": "Vout", "region": "r"},
                {"name": "c3", "bias": "Vout", "region": "r2"},
            ],
            "plan": {"floating": ["Vout"]},
            "regions": [],
        }

    def test_floating_sources_are_not_drivable(self) -> None:
        groups = run.contact_bias_names(self.payload())

        assert "Vin" in groups
        assert "Vout" not in groups, "부유는 걸어 줄 대상이 아니다"

    def test_a_driven_source_keeps_all_its_contacts(self) -> None:
        payload = self.payload()
        payload["plan"]["floating"] = []

        groups = run.contact_bias_names(payload)

        assert sorted(groups) == ["Vin", "Vout"]
        assert groups["Vout"] == ["c2", "c3"]

    def test_currents_still_report_the_floating_electrode(self) -> None:
        """전류는 여전히 읽어야 한다. 부유여도 전류는 흐른다."""
        source = (
            Path(__file__).resolve().parents[3] / "docker" / "devsim" / "run.py"
        ).read_text()
        body = source[source.index("def currents") :]
        body = body[: body.index("\n\n")]

        assert "floating" not in body, (
            "currents() 는 부유를 걸러내면 안 된다 — 전류는 접촉마다 읽는다"
        )


class TestFloatingVoltagesInTheResult:
    """풀어서 얻은 전압이 결과에 실려야 한다.

    이것이 이 기능의 산출물이다 — 전류 곡선이 아니라 **전압 곡선**(VTC)이
    나온다. `_read_dataset`(`service.py`)과 `scan_devsim_progress` 는 행 dict 를
    통째로 다루므로 키가 늘어도 그대로 통과한다.
    """

    def test_the_solver_can_read_a_circuit_node(self) -> None:
        source = (
            Path(__file__).resolve().parents[3] / "docker" / "devsim" / "run.py"
        ).read_text()

        assert "get_circuit_node_value" in source

    def test_rows_carry_the_voltages(self) -> None:
        source = (
            Path(__file__).resolve().parents[3] / "docker" / "devsim" / "run.py"
        ).read_text()
        tail = source[source.index('"currents": solver.currents()') :]

        assert '"voltages"' in tail[:400], "행에 전압을 실어야 한다"

    def test_no_floating_means_no_extra_key(self) -> None:
        """부유가 없으면 행 모양이 예전과 같아야 한다 — 기존 결과와 섞이므로."""
        solver = FakeSolver(lambda v: False)
        solver.payload = {"plan": {"floating": []}, "contacts": [], "regions": []}

        assert run.Solver.voltages(solver) == {}
