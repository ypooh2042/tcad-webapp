"""DevSim 소자 해석 실행기. **컨테이너 이미지에 구워 넣는다.**

사용자는 이 파일을 못 바꾼다. 읽는 것은 `/work/device.json` 하나이고, 그 안에는
좌표·요소·도핑·바이어스 계획만 들어 있다 — 코드가 될 수 있는 것은 없다.

내는 것:
  iv.jsonl  바이어스 점마다 한 줄. 다 풀 때까지 기다리지 않고 흘려보내므로
            진행률을 셀 수 있고, 중간에 죽어도 거기까지는 남는다.
  iv.json   끝난 뒤의 전체 결과.

단위: 좌표 cm, 농도 cm⁻³ (DevSim 규약). 2 차원이라 전류는 폭 방향 단위길이당
값이다. DevSim 이 A/cm 로 주는 것을 A/µm 로 바꿔 적는다 — 소자 쪽에서 쓰는 단위다.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

import devsim as ds
from devsim.python_packages.model_create import CreateSolution
from devsim.python_packages.simple_physics import (
    CreateOxideContact,
    CreateOxidePotentialOnly,
    CreateSiliconDriftDiffusion,
    CreateSiliconDriftDiffusionAtContact,
    CreateSiliconOxideInterface,
    CreateSiliconPotentialOnly,
    CreateSiliconPotentialOnlyContact,
    CreateSiliconSiliconInterface,
    GetContactBiasName,
    SetOxideParameters,
    SetSiliconParameters,
)

WORK = Path("/work")
DEVICE = "device"
MESH = "mesh"

#: A/cm → µA/µm.
#:
#: 2 차원 해석이라 전류는 폭 방향 단위길이당 값이다(세 번째 축이 모형에 없다).
#: DevSim 은 z 두께를 1 cm 로 놓고 풀어 A/cm 을 준다. 소자 쪽에서는 폭 1 µm 당
#: 마이크로암페어로 인용하는 것이 관례라 거기에 맞춘다.
PER_CM_TO_MICRO_PER_UM = 1.0e-4 * 1.0e6

#: 바이어스를 한 번에 이만큼 넘게 옮기지 않는다. 크게 뛰면 뉴턴이 못 따라간다.
MAX_BIAS_STEP = 0.25

#: 걸음을 몇 번까지 반으로 줄여 보는가. 0.25 V 에서 세 번이면 0.031 V 다.
#: 더 쪼개도 안 풀리는 자리는 걸음 크기 문제가 아니라 수렴 기준 쪽 문제이고
#: (`_TRANSPORT_RELAXED` 참조), 한 번 더 줄일 때마다 그 점에 드는 solve 횟수가
#: 두 배가 된다 — 못 넘을 벽에서 시간만 태운다.
MAX_BISECTIONS = 3

#: 부유 노드를 접지로 잇는 저항(Ω).
#:
#: **왜 필요한가.** 전위만 푸는 평형 단계에서는 회로 노드 행이 빈다 —
#: `CreateSiliconPotentialOnlyContact(is_circuit=True)` 가 만드는 접촉
#: 방정식에 전하만 있고 전류 모델이 없기 때문이다
#: (`simple_physics.py` 의 `contact_equation` 참조). 그 상태로는 행렬이
#: 특이해져 평형해부터 실패한다. 실측: pn 접합 두 개를 한 노드에 걸어도
#: 저항 없이는 평형 단계에서 안 풀렸고, 저항을 매다니 풀렸다.
#:
#: **왜 결과에 영향이 없는가.** 1e12 Ω 이면 5 V 에서 5 pA 다. 이 앱이 다루는
#: 전류는 µA 대라 여섯 자리 아래다.
SHUNT_OHMS = float(os.environ.get("TCAD_SHUNT_OHMS", "1e12"))

_DC = dict(type="dc", solver_type="direct")

#: 수렴 기준. DevSim 자체 MOS 시험(`testing/mos_2d_create.py`)의 값을 그대로 쓴다.
#:
#: 다이오드 예제의 값(abs 1e10 / rel 1e-10)을 쓰면 안 된다. off 상태의 공핍층에서
#: 전자 밀도가 1e-30 대로 떨어지는데, 거기서 **상대** 오차는 의미가 없다. 실측에서
#: Vg=0·Vd=1V 를 못 넘기고 상대오차 2.8e-4 에 갇혔다 — 메시를 완전히 새로 짜도
#: 같은 자리에서 멈췄으므로 메시가 아니라 이 기준이 원인이었다.
_EQUILIBRIUM = dict(absolute_error=1.0e-13, relative_error=1.0e-12, maximum_iterations=30)
_TRANSPORT = dict(absolute_error=1.0e30, relative_error=1.0e-5, maximum_iterations=30)

#: 엄격한 기준으로 안 풀렸을 때 **한 번만** 느슨하게 다시 본다.
#:
#: 어려운 바이어스에서 뉴턴이 한계 순환에 빠지는 일이 있다 — 실측한 CMOS
#: 인버터 부하선에서 RelError 가 4.4e-3 과 3.8e-5 사이를 오가며 1e-5 아래로
#: 내려가지 못했다. 그때 AbsError 는 내내 2.5e4 였다. 실제로 전류가 흐를 때의
#: 절대오차가 1e16~1e18 인 것과 견주면 사실상 0 이다. 즉 **답은 이미 충분히
#: 정확한데 상대 기준만 못 넘고 있었다.**
#:
#: 기본을 느슨하게 하지 않는 이유: 지금 기준으로 잘 풀리는 결과들(검증해 둔
#: nMOS I-V 포함)을 건드리지 않기 위해서다. 막힌 점만 이 기준으로 구제하고,
#: 몇 점이 그렇게 구제됐는지 결과에 적어 둔다.
_TRANSPORT_RELAXED = dict(
    absolute_error=1.0e30, relative_error=1.0e-4, maximum_iterations=50
)


def load() -> dict:
    return json.loads((WORK / "device.json").read_text())


def build_device(payload: dict) -> None:
    mesh = payload["mesh"]
    ds.create_gmsh_mesh(
        mesh=MESH,
        coordinates=mesh["coordinates"],
        elements=mesh["elements"],
        physical_names=mesh["physical_names"],
    )
    for region in payload["regions"]:
        ds.add_gmsh_region(
            mesh=MESH,
            gmsh_name=region["name"],
            region=region["name"],
            material=region["devsim_material"],
        )
    for interface in payload["interfaces"]:
        ds.add_gmsh_interface(
            mesh=MESH,
            gmsh_name=interface["name"],
            name=interface["name"],
            region0=interface["region0"],
            region1=interface["region1"],
        )
    for contact in payload["contacts"]:
        ds.add_gmsh_contact(
            mesh=MESH,
            gmsh_name=contact["name"],
            name=contact["name"],
            region=contact["region"],
            material="metal",
        )
    ds.finalize_mesh(mesh=MESH)
    ds.create_device(mesh=MESH, device=DEVICE)


def apply_doping(payload: dict) -> None:
    """노드마다 NetDoping 을 심는다.

    DevSim 의 노드 순서를 맞히려 들지 않는다. `x`/`y` 를 되읽어 우리가 보낸
    좌표로 찾는다 — 순서를 가정하면 DevSim 이 순서를 바꾸는 날 조용히 틀린다.
    """
    digits = payload["coordinate_digits"]
    for name, points in payload["doping"].items():
        lookup = {(round(x, digits), round(y, digits)): value for x, y, value in points}
        xs = ds.get_node_model_values(device=DEVICE, region=name, name="x")
        ys = ds.get_node_model_values(device=DEVICE, region=name, name="y")
        missing = 0
        values = []
        for x, y in zip(xs, ys):
            key = (round(x, digits), round(y, digits))
            if key not in lookup:
                missing += 1
            values.append(lookup.get(key, 0.0))
        if missing:
            # 조용히 0 을 넣으면 도핑 없는 소자가 되어 곡선이 이상해진다.
            print(f"경고: {name} 의 노드 {missing}/{len(values)} 개가 좌표로 안 찾아짐")
        ds.node_solution(device=DEVICE, region=name, name="NetDoping")
        ds.set_node_values(device=DEVICE, region=name, name="NetDoping", values=values)


def setup_physics(payload: dict) -> None:
    temperature = payload["temperature_k"]
    semiconductors = [r["name"] for r in payload["regions"] if r["is_semiconductor"]]
    insulators = [r["name"] for r in payload["regions"] if not r["is_semiconductor"]]

    for name in semiconductors:
        SetSiliconParameters(DEVICE, name, temperature)
    for name in insulators:
        SetOxideParameters(DEVICE, name, temperature)

    apply_doping(payload)

    for name in semiconductors:
        CreateSolution(DEVICE, name, "Potential")
        CreateSiliconPotentialOnly(DEVICE, name)
    for name in insulators:
        CreateOxidePotentialOnly(DEVICE, name)

    semiconductor_names = set(semiconductors)
    floating = set(payload["plan"].get("floating") or ())
    for node in sorted(floating):
        # 전위를 풀어서 얻을 노드. 접지로 가는 아주 큰 저항을 함께 매단다
        # (이유는 `SHUNT_OHMS` 주석).
        ds.add_circuit_node(name=node, variable_update="default")
        ds.circuit_element(name=f"R_{node}", n1=node, n2="0", value=SHUNT_OHMS)

    for contact in payload["contacts"]:
        is_floating = contact["bias"] in floating
        if is_floating:
            # **파라미터를 걸면 안 된다.** 같은 이름의 장치 파라미터가 있으면
            # 회로 별칭이 무력화되어 수렴이 깨진다(실측: 출력이 0 에 붙박이).
            ds.circuit_node_alias(
                node=contact["bias"], alias=GetContactBiasName(contact["name"])
            )
        else:
            ds.set_parameter(
                device=DEVICE, name=GetContactBiasName(contact["name"]), value=0.0
            )
        if contact["region"] in semiconductor_names:
            CreateSiliconPotentialOnlyContact(
                DEVICE, contact["region"], contact["name"], is_circuit=is_floating
            )
        else:
            CreateOxideContact(DEVICE, contact["region"], contact["name"])

    for interface in payload["interfaces"]:
        both = (
            interface["region0"] in semiconductor_names
            and interface["region1"] in semiconductor_names
        )
        if both:
            CreateSiliconSiliconInterface(DEVICE, interface["name"])
        else:
            CreateSiliconOxideInterface(DEVICE, interface["name"])


def add_drift_diffusion(payload: dict) -> None:
    semiconductors = [r["name"] for r in payload["regions"] if r["is_semiconductor"]]
    for name in semiconductors:
        CreateSolution(DEVICE, name, "Electrons")
        CreateSolution(DEVICE, name, "Holes")
        ds.set_node_values(
            device=DEVICE, region=name, name="Electrons", init_from="IntrinsicElectrons"
        )
        ds.set_node_values(
            device=DEVICE, region=name, name="Holes", init_from="IntrinsicHoles"
        )
        CreateSiliconDriftDiffusion(DEVICE, name)

    floating = set(payload["plan"].get("floating") or ())
    for contact in payload["contacts"]:
        if contact["region"] in set(semiconductors):
            CreateSiliconDriftDiffusionAtContact(
                DEVICE,
                contact["region"],
                contact["name"],
                is_circuit=contact["bias"] in floating,
            )


def solution_names(region: dict) -> list[str]:
    """그 영역이 들고 있는 미지수들."""
    if region["is_semiconductor"]:
        return ["Potential", "Electrons", "Holes"]
    return ["Potential"]


def snapshot(payload: dict) -> dict[str, dict[str, list[float]]]:
    """지금 해를 통째로 떠 둔다.

    수렴에 실패하면 뉴턴이 헤매다 만 값이 그대로 남는다. 그 상태에서 다음 점을
    풀면 거기서도 실패하고, 한 점이 안 풀린 것이 곡선 전체를 잃는 것으로 번진다.
    그래서 마지막으로 성공한 자리로 되돌린 뒤 다음 점으로 넘어간다.
    """
    return {
        region["name"]: {
            # `list(...)` 로 감싸지 않는다. `set_node_values` 가
            # `array.array('d')` 를 그대로 받으므로, 감싸면 float 객체가 노드
            # 수만큼 생겨 메모리가 4 배가 된다(cmos 기준 1.2 MB → 4.8 MB).
            name: ds.get_node_model_values(
                device=DEVICE, region=region["name"], name=name
            )
            for name in solution_names(region)
        }
        for region in payload.get("regions", ())
    }


def restore(state: dict[str, dict[str, list[float]]]) -> None:
    for region, models in state.items():
        for name, values in models.items():
            ds.set_node_values(
                device=DEVICE, region=region, name=name, values=values
            )


def contact_bias_names(payload: dict) -> dict[str, list[str]]:
    """전압원 이름 → 그 전압원이 물고 있는 DevSim 접촉들.

    **부유 전압원은 빠진다.** 걸어 줄 전압이 없기 때문이기도 하지만, 더
    중요하게는 `Solver._set` 이 `ds.set_parameter` 를 부르는데 부유 접촉에
    그 파라미터가 생기면 회로 별칭이 무력화되어 수렴이 깨진다(실측). 아예
    목록에서 빼서 실수로도 걸리지 않게 한다.
    """
    floating = set(payload.get("plan", {}).get("floating") or ())
    grouped: dict[str, list[str]] = {}
    for contact in payload["contacts"]:
        if contact["bias"] in floating:
            continue
        grouped.setdefault(contact["bias"], []).append(contact["name"])
    return grouped


def _stall_reason(info: dict | None) -> str:
    """어디서 막혔는지 한 줄로. 이 문구가 결과 파일의 `reason` 이 된다.

    지금까지는 어느 노드가 수렴을 막았는지 알려면 컨테이너 로그를 사람이
    읽어야 했다. 그 정보를 결과에 실어 준다.

    회로 노드가 있으면 `info["iterations"][k]["circuit"]` 이 `"devices"` 와
    나란히 들어온다. 소자 쪽에서 범인을 못 찾으면 그쪽을 본다.
    """
    steps = (info or {}).get("iterations") or ()
    if not steps:
        return "수렴 실패"
    last = steps[-1]
    worst = None
    for device in last.get("devices") or ():
        for region in device.get("regions") or ():
            for equation in region.get("equations") or ():
                rel = equation.get("relative_error") or 0.0
                if worst is None or rel > worst[0]:
                    worst = (rel, region.get("name"), equation)
    if worst is None:
        circuit = last.get("circuit")
        if circuit:
            return (
                f"수렴 실패 (회로 노드, RelError "
                f"{circuit.get('relative_error', 0.0):.2e})"
            )
        return "수렴 실패"
    rel, region, equation = worst
    return (
        f"수렴 실패 (RelError {rel:.2e}, {equation.get('name')}, "
        f"region={region}, node={equation.get('relative_error_node')})"
    )


class Solver:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.groups = contact_bias_names(payload)
        self.applied: dict[str, float] = {name: 0.0 for name in self.groups}
        self._reset_counters()

    def _reset_counters(self) -> None:
        """계측용 카운터. 시험이 만드는 가짜 Solver 도 이것만 부르면 된다."""
        #: 느슨한 기준으로 구제한 solve 횟수.
        self.relaxed = 0
        #: 부른 solve 횟수와 그 안에서 돈 뉴턴 반복의 총합.
        #:
        #: 솔버를 손볼 때 좋아졌는지 나빠졌는지는 **반복 횟수**로 재는 것이
        #: 벽시계 시간보다 훨씬 정확하다. `OPENBLAS_NUM_THREADS=1` 이라 같은
        #: 입력이면 반복 횟수가 비트 단위로 재현되는 반면, 시간은 그때그때
        #: 부하에 흔들려 작은 차이를 가린다(실측으로 겪었다).
        self.solves = 0
        self.newton = 0

    def _set(self, bias: str, value: float) -> None:
        for contact in self.groups[bias]:
            ds.set_parameter(
                device=DEVICE, name=GetContactBiasName(contact), value=value
            )

    def solve(self) -> None:
        """푼다. 엄격한 기준으로 안 되면 한 번만 느슨하게 다시 본다.

        느슨한 쪽으로 풀린 횟수는 세어 둔다 — 결과의 품질을 사용자가 알아야
        한다. 이유는 `_TRANSPORT_RELAXED` 주석 참조.
        """
        ok, error, _ = self._solve_once(_TRANSPORT)
        if ok:
            return

        ok, relaxed_error, info = self._solve_once(_TRANSPORT_RELAXED)
        if ok:
            self.relaxed += 1
            return

        # 둘 다 안 풀렸다. 구제된 것이 아니므로 relaxed 는 올리지 않는다.
        raise relaxed_error or error or RuntimeError(_stall_reason(info))

    def _solve_once(self, criteria: dict):
        """한 번 푼다. `(풀렸나, 올릴 예외 또는 None, info)`.

        **`info=True` 는 실패를 예외가 아니라 반환값으로 알린다.** 실측:

            info 없이 : 예외를 올린다   devsim.error("Convergence failure!")
            info=True : 예외 없이 반환   {"converged": False, ...}

        이 클래스의 나머지(`_try`·`ramp_to`·`reached`)는 전부 예외로 실패를
        판정하므로, 그냥 켜면 모든 수렴 실패가 조용히 성공으로 둔갑하고 발산한
        값으로 전류를 읽어 **틀린 곡선이 정상 결과로 나간다.** 그래서 여기서
        `converged` 를 직접 보고 판정을 되살린다.
        """
        try:
            info = ds.solve(**criteria, **_DC, info=True)
        except Exception as error:
            # 특이 행렬 같은 진짜 예외. 원문을 그대로 올려 문구를 지킨다.
            return False, error, None
        self.solves += 1
        self.newton += len(info.get("iterations") or ())
        return bool(info.get("converged")), None, info

    def _try(self, bias: str, value: float) -> bool:
        """한 걸음 딛어 본다. 성공하면 그 자리를 굳히고 참."""
        self._set(bias, value)
        try:
            self.solve()
        except Exception:
            # 못 풀었으면 걸어 둔 전압을 되돌린다. 남겨 두면 다음 시도가
            # 어디서 출발하는지 알 수 없다.
            self._set(bias, self.applied[bias])
            return False
        self.applied[bias] = value
        return True

    def reached(self, bias: str, target: float) -> float:
        """목표까지 갈 수 있는 데까지 가고, **닿은 전압**을 돌려준다.

        `ramp_to` 와 달리 실패해도 예외를 내지 않고, 되돌리지도 않는다.
        벽에 부딪힌 자리를 그대로 붙들고 있는다.

        **걸음이 실패하면 반으로 줄여 다시 딛는다.** 이것이 없으면 0.25 V 로
        못 넘는 자리에서 그냥 포기했고, 더 나쁘게는 그 뒤의 모든 점이 같은
        자리에서 출발해 같은 첫 걸음을 다시 밟아 반드시 같이 실패했다
        (실측: CMOS 인버터 부하선 38 점 중 27 점이 그렇게 버려졌는데,
        정작 진짜로 어려운 점은 하나였다).
        """
        current = self.applied[bias]
        span = target - current
        if span == 0.0:
            return current

        step = MAX_BIAS_STEP
        shrinks = 0
        while True:
            remaining = target - self.applied[bias]
            if abs(remaining) <= 1e-12:
                return self.applied[bias]
            reach = min(step, abs(remaining))
            value = self.applied[bias] + reach * (1.0 if remaining > 0 else -1.0)
            if self._try(bias, value):
                continue
            if shrinks >= MAX_BISECTIONS:
                return self.applied[bias]
            step /= 2.0
            shrinks += 1

    def ramp_to(self, bias: str, target: float) -> None:
        """전압을 목표까지 옮긴다. 한 번에 뛰면 뉴턴이 못 따라간다.

        닿지 못하면 **걸어 둔 전압을 원래대로 되돌리고** 예외를 올린다.
        중간까지 올라간 채로 두면 다음 점이 어디서 출발하는지 알 수 없다.
        """
        current = self.applied[bias]
        landed = self.reached(bias, target)
        if abs(landed - target) > 1e-12:
            self._set(bias, current)
            self.applied[bias] = current
            raise RuntimeError(
                f"{bias} 를 {target:g} V 까지 올리지 못했습니다 "
                f"({landed:g} V 에서 막힘)"
            )

    def reset_to(self, applied: dict[str, float]) -> None:
        """걸어 둔 전압을 통째로 되돌린다. 해를 되돌릴 때 같이 부른다."""
        for bias, value in applied.items():
            self._set(bias, value)
        self.applied = dict(applied)

    def voltages(self) -> dict[str, float]:
        """부유 전압원의 **풀어서 얻은** 전위(V).

        이것이 이 기능의 산출물이다 — 인버터라면 입력 대 출력 곡선(VTC)이
        여기서 나온다. 부유가 없으면 빈 dict 라 행 모양이 예전과 같다.
        """
        nodes = self.payload.get("plan", {}).get("floating") or ()
        return {
            node: ds.get_circuit_node_value(solution="dcop", node=node)
            for node in nodes
        }

    def currents(self) -> dict[str, float]:
        """전압원별 전류(A/µm). 산화막에만 붙은 전압원은 전류가 없다."""
        semiconductors = {
            r["name"] for r in self.payload["regions"] if r["is_semiconductor"]
        }
        totals: dict[str, float] = {}
        for contact in self.payload["contacts"]:
            if contact["region"] not in semiconductors:
                totals.setdefault(contact["bias"], 0.0)
                continue
            electrons = ds.get_contact_current(
                device=DEVICE,
                contact=contact["name"],
                equation="ElectronContinuityEquation",
            )
            holes = ds.get_contact_current(
                device=DEVICE,
                contact=contact["name"],
                equation="HoleContinuityEquation",
            )
            totals[contact["bias"]] = totals.get(contact["bias"], 0.0) + (
                electrons + holes
            ) * PER_CM_TO_MICRO_PER_UM
        return totals


def run(payload: dict) -> dict:
    plan = payload["plan"]
    sweep_name = plan["sweep"]["bias"]
    sweep_values = plan["sweep"]["values"]

    solver = Solver(payload)

    # 평형해. 전위만 푼 뒤 드리프트-확산을 얹는다. 바로 DD 로 가면 거의 안 풀린다.
    # 두 번 부르는 것은 DevSim 의 MOS 시험이 하는 그대로다 — 첫 번째가 큰 폭으로
    # 움직이고 두 번째가 다듬는다.
    ds.solve(**_EQUILIBRIUM, **_DC)
    ds.solve(**_EQUILIBRIUM, **_DC)
    add_drift_diffusion(payload)
    solver.solve()

    # **켜는 길을 골라서 간다.** 직류 정상상태에는 이력이 없으므로 어느 길로
    # 가든 답은 같다. 그런데 부유 노드가 있으면 길이 수렴을 가른다.
    #
    # 인버터에서 입력이 0 인 채로 VDD 를 올리면 nMOS 가 꺼져 있어 출력 노드가
    # 누설과 접지 저항으로만 정해진다. 그 약한 결정성이 자코비안을 나쁘게 만들어
    # 뉴턴이 한계 순환에 빠진다(실측: 1.53 V 에서 막힘).
    #
    # 스윕 전압원을 먼저 중간값으로 올려 두면 두 소자가 함께 켜져 출력이
    # 단단히 정해진다. 그 상태에서 상수를 올리고, 마지막에 스윕을 제자리로
    # 데려온다.
    warm = None
    if plan.get("floating") and sweep_values:
        warm = 0.5 * (min(sweep_values) + max(sweep_values))
        if warm != solver.applied.get(sweep_name):
            solver.ramp_to(sweep_name, warm)

    for name, value in plan["constants"].items():
        solver.ramp_to(name, value)

    # **스윕을 가운데에서 바깥으로 걷는다.**
    #
    # 인버터의 전환 구간(두 소자가 함께 켜져 출력이 급변하는 곳)을 한 번에
    # 건너뛰면 못 넘는다 — 실측으로 2.5 V 에서 0 V 로 가다 1.72 V 에서 섰다.
    # 온기를 넣은 자리에서 가장 가까운 점부터 시작해 한쪽 끝까지 간 뒤,
    # 그 자리로 돌아와 반대쪽으로 걸으면 매 걸음이 스윕 간격만큼이라 각 걸음이
    # 바로 앞의 수렴한 해에서 출발한다.
    #
    # 직류 정상상태에는 이력이 없으므로 순서가 답을 바꾸지 않는다. 행 순서는
    # 뒤섞이지만 화면이 x 로 정렬해 그린다(`figures.ts`).
    walk = list(sweep_values)
    turn = 0
    if warm is not None:
        upper = sorted(v for v in sweep_values if v >= warm)
        lower = sorted((v for v in sweep_values if v < warm), reverse=True)
        walk = upper + lower
        turn = len(upper)

    # 여기까지가 모든 곡선의 출발점이다. 한 곡선이 통째로 안 풀렸을 때 돌아온다.
    baseline = snapshot(payload)
    baseline_bias = dict(solver.applied)

    stream = (WORK / "iv.jsonl").open("w")
    rows: list[dict] = []
    failures: list[dict] = []

    def record(row: dict) -> None:
        stream.write(json.dumps(row) + "\n")
        stream.flush()

    def give_up(
        combination: dict,
        value: float | None,
        error: Exception,
        newton: int = 0,
    ) -> None:
        """안 풀린 점을 적어 두고 넘어간다.

        점 하나가 안 풀렸다고 해석을 통째로 버리지 않는다. 스윕 끝쪽 몇 점이
        발산하는 것은 흔한 일이고, 그 앞의 곡선은 멀쩡하다.
        """
        # devsim 의 오류 문구는 줄바꿈이 붙어 온다. 화면에 그대로 내보내면
        # 목록이 한 줄씩 벌어진다.
        reason = str(error).strip() or error.__class__.__name__
        entry = {
            "sweep": value,
            "steps": dict(combination),
            "reason": reason,
            "newton": newton,
        }
        failures.append(entry)
        record({**entry, "ok": False})
        print(
            f"수렴 실패, 이 점은 건너뜁니다: {combination} {sweep_name}={value} — {reason}",
            file=sys.stderr,
        )

    #: 직전 곡선의 **시작점** 상태. 다음 곡선으로 넘어갈 때 여기로 되돌린다.
    curve_start: tuple[dict, dict[str, float]] | None = None

    try:
        for combination in plan["steps"]:
            # 옮길 곳이 있을 때만 알린다. 단계 전압원이 없으면 곡선이 하나뿐이라
            # 옮기는 일 자체가 없다 — 그때도 표시를 내보내면 진행률이 빈
            # 문구로 시작한다.
            if combination or curve_start is not None:
                record({"phase": "moving", "steps": dict(combination)})
            try:
                if curve_start is not None:
                    # **되감지 않고 되돌린다.**
                    #
                    # 스윕은 곡선마다 처음부터 훑으므로, 앞 곡선이 끝난 자리
                    # (스윕 전압의 끝)에서 시작으로 내려와야 한다. 예전에는 그
                    # 길을 0.25V 씩 실제로 풀어 내려왔다 — 실측으로 전환 한 번에
                    # solve 12회 5.5초였고 그중 8회가 이 되감기였다. 그동안
                    # 화면은 한 칸도 안 움직인다.
                    #
                    # 직류 정상상태에는 이력이 없다. 곡선 시작점의 해를 이미
                    # 떠 두었으므로 그대로 복원하면 같은 자리에 한 번에 선다.
                    restore(curve_start[0])
                    solver.reset_to(curve_start[1])
                for name, value in combination.items():
                    solver.ramp_to(name, value)
                solver.ramp_to(sweep_name, walk[0])
            except Exception as error:
                # 곡선의 출발점부터 안 풀렸다. 이 조합은 통째로 못 얻는다.
                restore(baseline)
                solver.reset_to(baseline_bias)
                curve_start = None
                for value in sweep_values:
                    give_up(combination, value, error)
                continue

            # 이 곡선의 시작 상태. 다음 곡선이 여기로 돌아온다.
            curve_start = (snapshot(payload), dict(solver.applied))

            for index, value in enumerate(walk):
                if turn and index == turn:
                    # 위쪽 끝까지 왔다. 온기 자리로 돌아가 아래쪽을 걷는다.
                    restore(curve_start[0])
                    solver.reset_to(curve_start[1])
                # **간 만큼은 지킨다.** 예전에는 못 닿으면 마지막으로 성공한
                # 자리로 되돌렸는데, 그러면 다음 점이 같은 자리에서 출발해
                # 방금 실패한 그 첫 걸음을 다시 밟는다 — 반드시 또 실패한다.
                # 그래서 어려운 점 하나가 곡선의 나머지를 통째로 무너뜨렸다
                # (실측: 38 점 중 27 점이 그렇게 버려졌다).
                #
                # `reached` 가 서는 자리는 언제나 실제로 풀린 해이므로, 거기
                # 그대로 두고 다음 목표로 이어 걸으면 된다.
                spent = solver.newton
                landed = solver.reached(sweep_name, value)
                spent = solver.newton - spent
                if abs(landed - value) > 1e-12:
                    give_up(
                        combination,
                        value,
                        RuntimeError(f"{landed:g} V 에서 막혔습니다"),
                        newton=spent,
                    )
                    continue

                solved = solver.voltages()
                row = {
                    "sweep": value,
                    "steps": dict(combination),
                    "currents": solver.currents(),
                    #: 부유 노드의 전위. 없으면 키 자체가 없어 예전 행과 같다.
                    **({"voltages": solved} if solved else {}),
                    "ok": True,
                    #: 이 점을 얻는 데 든 뉴턴 반복.
                    "newton": spent,
                }
                rows.append(row)
                record(row)
    finally:
        stream.close()

    return {
        "sweep": sweep_name,
        "steps": [b for b in plan["steps"][0]] if plan["steps"] else [],
        "biases": sorted(solver.groups),
        "current_unit": "uA/um",
        "rows": rows,
        "failures": failures,
        "total": plan["total"],
        "completed": len(rows),
        #: 계측. 솔버를 손볼 때 좋아졌는지 나빠졌는지를 **벽시계 시간 대신
        #: 이 숫자로** 판단한다 — 시간은 그때그때 부하에 흔들려 작은 차이를
        #: 가리는 반면, 반복 횟수는 같은 입력이면 비트 단위로 재현된다.
        "stats": {
            "solves": solver.solves,
            "newton": solver.newton,
            "relaxed": solver.relaxed,
        },
        "error": None,
    }


def main() -> int:
    payload = load()
    build_device(payload)
    setup_physics(payload)
    result = run(payload)
    (WORK / "iv.json").write_text(json.dumps(result))
    # 한 점도 못 얻었으면 실패다. 몇 점을 건너뛴 것은 실패가 아니다 — 사용자가
    # 볼 곡선이 남아 있고, 어느 점이 빠졌는지도 함께 알려준다.
    return 0 if result["rows"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
