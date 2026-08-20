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

#: A/cm → A/µm.
PER_CM_TO_PER_UM = 1.0e-4

#: 바이어스를 한 번에 이만큼 넘게 옮기지 않는다. 크게 뛰면 뉴턴이 못 따라간다.
MAX_BIAS_STEP = 0.25

_DC = dict(type="dc", solver_type="direct")

#: 수렴 기준. DevSim 자체 MOS 시험(`testing/mos_2d_create.py`)의 값을 그대로 쓴다.
#:
#: 다이오드 예제의 값(abs 1e10 / rel 1e-10)을 쓰면 안 된다. off 상태의 공핍층에서
#: 전자 밀도가 1e-30 대로 떨어지는데, 거기서 **상대** 오차는 의미가 없다. 실측에서
#: Vg=0·Vd=1V 를 못 넘기고 상대오차 2.8e-4 에 갇혔다 — 메시를 완전히 새로 짜도
#: 같은 자리에서 멈췄으므로 메시가 아니라 이 기준이 원인이었다.
_EQUILIBRIUM = dict(absolute_error=1.0e-13, relative_error=1.0e-12, maximum_iterations=30)
_TRANSPORT = dict(absolute_error=1.0e30, relative_error=1.0e-5, maximum_iterations=30)


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
    for contact in payload["contacts"]:
        ds.set_parameter(
            device=DEVICE, name=GetContactBiasName(contact["name"]), value=0.0
        )
        if contact["region"] in semiconductor_names:
            CreateSiliconPotentialOnlyContact(
                DEVICE, contact["region"], contact["name"]
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

    for contact in payload["contacts"]:
        if contact["region"] in set(semiconductors):
            CreateSiliconDriftDiffusionAtContact(
                DEVICE, contact["region"], contact["name"]
            )


def contact_bias_names(payload: dict) -> dict[str, list[str]]:
    """전압원 이름 → 그 전압원이 물고 있는 DevSim 접촉들."""
    grouped: dict[str, list[str]] = {}
    for contact in payload["contacts"]:
        grouped.setdefault(contact["bias"], []).append(contact["name"])
    return grouped


class Solver:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.groups = contact_bias_names(payload)
        self.applied: dict[str, float] = {name: 0.0 for name in self.groups}

    def _set(self, bias: str, value: float) -> None:
        for contact in self.groups[bias]:
            ds.set_parameter(
                device=DEVICE, name=GetContactBiasName(contact), value=value
            )

    def solve(self) -> None:
        ds.solve(**_TRANSPORT, **_DC)

    def ramp_to(self, bias: str, target: float) -> None:
        """전압을 조금씩 옮긴다. 한 번에 뛰면 뉴턴이 못 따라간다."""
        current = self.applied[bias]
        span = target - current
        steps = max(1, int(abs(span) / MAX_BIAS_STEP + 0.999))
        for index in range(1, steps + 1):
            value = current + span * index / steps
            self._set(bias, value)
            self.solve()
            self.applied[bias] = value

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
            ) * PER_CM_TO_PER_UM
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

    for name, value in plan["constants"].items():
        solver.ramp_to(name, value)

    stream = (WORK / "iv.jsonl").open("w")
    rows: list[dict] = []
    failure: str | None = None

    try:
        for combination in plan["steps"]:
            for name, value in combination.items():
                solver.ramp_to(name, value)
            # 스윕은 늘 처음부터 다시 훑는다. 앞 곡선의 끝에서 이어가면 첫 점이
            # 이력에 오염된다.
            solver.ramp_to(sweep_name, sweep_values[0])
            for value in sweep_values:
                solver.ramp_to(sweep_name, value)
                row = {
                    "sweep": value,
                    "steps": dict(combination),
                    "currents": solver.currents(),
                }
                rows.append(row)
                stream.write(json.dumps(row) + "\n")
                stream.flush()
    except Exception as error:  # devsim 은 수렴 실패를 예외로 던진다
        failure = str(error) or error.__class__.__name__
        print(f"해석이 중간에 멈췄습니다: {failure}", file=sys.stderr)
    finally:
        stream.close()

    return {
        "sweep": sweep_name,
        "steps": [b for b in plan["steps"][0]] if plan["steps"] else [],
        "biases": sorted(solver.groups),
        "current_unit": "A/um",
        "rows": rows,
        "total": plan["total"],
        "completed": len(rows),
        "error": failure,
    }


def main() -> int:
    payload = load()
    build_device(payload)
    setup_physics(payload)
    result = run(payload)
    (WORK / "iv.json").write_text(json.dumps(result))
    if result["error"] and not result["rows"]:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
