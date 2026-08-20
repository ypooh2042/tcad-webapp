"""해석 스펙과 그 검증.

브라우저에서 온 값이 그대로 솔버로 들어간다. 스펙 자체는 코드가 아니지만(우리가
쓴 고정 스크립트가 읽는다) 크기와 짜임새는 사용자가 정한다. 여기서 막지 않으면
바이어스 점 10만 개짜리 요청이 컨테이너 안에서 타임아웃까지 돌게 된다.

전압원(`Bias`)과 전극(`ElectrodeChoice`)을 나눈 이유:

    전극은 **구조에서 나온다** — 같은 금속 덩어리는 같은 전위라는 규칙이
    등전위를 이미 보장한다.
    전압원은 **사용자가 만든다** — 서로 다른 전극을 하나로 묶고 싶을 때
    (기판을 소스에 단다) 쓰는 것이 이 계층이다.
"""

from __future__ import annotations

from enum import Enum
from itertools import product
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.devsim.electrodes import GateModel

#: 한 번의 해석에서 풀 수 있는 바이어스 점의 총수.
#: 실측(실리콘 1600 요소, 점당 수백 ms)을 근거로 잡은 값이다. 넘으면 잡 타임아웃에
#: 걸려 아무것도 못 건지는 것보다 미리 거절하는 편이 낫다.
MAX_TOTAL_POINTS = 300

#: 스윕 한 축의 최대 점수.
MAX_SWEEP_POINTS = 200

#: 전압 상한. 실제 소자에서 이보다 큰 값은 의미가 없고, 솔버는 발산한다.
MAX_ABS_VOLTS = 100.0


class BiasRole(str, Enum):
    """전압원이 스윕에서 맡는 자리.

    `SWEEP` 안쪽 루프. 정확히 하나. 곡선의 x 축이 된다.
    `STEP`  바깥 루프. 곡선족을 만든다(Id-Vd 의 Vgs).
    `CONST` 고정. 보통 소스와 기판이 0 이다.
    """

    SWEEP = "sweep"
    STEP = "step"
    CONST = "const"


class Box(BaseModel):
    """화면에서 찍은 사각 범위(µm). 이 안에 든 경계 변을 전극으로 삼는다."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float

    @model_validator(mode="after")
    def _ordered(self) -> Box:
        if self.x_min > self.x_max or self.y_min > self.y_max:
            raise ValueError("범위의 최소가 최대보다 큽니다")
        return self


class ElectrodeChoice(BaseModel):
    """해석에 쓸 전극 하나.

    `detected` 구조에서 자동으로 찾은 것. `key` 는 자동으로 붙은 이름
                (source/gate/drain/contactN)이고, 같은 구조·같은 게이트 모델이면
                항상 같게 나오므로 안정적인 열쇠다.
    `backside`  뒷면 경계 전체. 기판 접촉이 공정 코드에 없을 때 쓴다.
    `picked`    화면에서 찍은 상자 안의 경계.
    """

    origin: Literal["detected", "backside", "picked"]
    label: str = Field(min_length=1, max_length=32)
    key: str | None = Field(default=None, max_length=32)
    box: Box | None = None

    @model_validator(mode="after")
    def _needs_its_own_field(self) -> ElectrodeChoice:
        if self.origin == "detected" and not self.key:
            raise ValueError("자동 추출 전극에는 key 가 필요합니다")
        if self.origin == "picked" and self.box is None:
            raise ValueError("화면에서 찍은 전극에는 범위가 필요합니다")
        return self


class SweepRange(BaseModel):
    start: float = Field(ge=-MAX_ABS_VOLTS, le=MAX_ABS_VOLTS)
    stop: float = Field(ge=-MAX_ABS_VOLTS, le=MAX_ABS_VOLTS)
    step: float = Field(gt=0.0, le=MAX_ABS_VOLTS)


class Bias(BaseModel):
    """전압원 하나. 연결된 전극들이 같은 전위를 갖는다."""

    name: str = Field(min_length=1, max_length=32)
    electrodes: list[str] = Field(min_length=1, max_length=8)
    role: BiasRole
    value: float | None = Field(default=None, ge=-MAX_ABS_VOLTS, le=MAX_ABS_VOLTS)
    values: list[float] | None = Field(default=None, max_length=16)
    sweep: SweepRange | None = None

    @model_validator(mode="after")
    def _matches_its_role(self) -> Bias:
        if self.role is BiasRole.CONST and self.value is None:
            raise ValueError(f"{self.name}: 고정 전압원에는 전압이 필요합니다")
        if self.role is BiasRole.STEP and not self.values:
            raise ValueError(f"{self.name}: 단계 전압원에는 전압 목록이 필요합니다")
        if self.role is BiasRole.SWEEP and self.sweep is None:
            raise ValueError(f"{self.name}: 스윕 전압원에는 스윕 범위가 필요합니다")
        if self.values and any(abs(v) > MAX_ABS_VOLTS for v in self.values):
            raise ValueError(f"{self.name}: 전압이 너무 큽니다")
        return self

    def points(self) -> list[float]:
        """이 전압원이 훑는 전압들."""
        if self.role is BiasRole.CONST:
            return [self.value or 0.0]
        if self.role is BiasRole.STEP:
            return list(self.values or [])
        assert self.sweep is not None
        return sweep_values(self.sweep.start, self.sweep.stop, self.sweep.step)


class DeviceSpec(BaseModel):
    """해석 한 번의 전부."""

    electrodes: list[ElectrodeChoice] = Field(min_length=1, max_length=16)
    biases: list[Bias] = Field(min_length=1, max_length=8)
    gate_model: GateModel = GateModel.SEMICONDUCTOR
    temperature_k: float = Field(default=300.0, gt=0.0, le=1000.0)
    #: 사용자가 붙인 이름. 비교 화면의 범례에 그대로 나온다.
    label: str = Field(default="해석", min_length=1, max_length=120)
    #: 어느 구조에서 왔는지. **서버가 채운다** — 브라우저가 보낸 값은 덮어쓴다.
    structure: str = Field(default="", max_length=255)

    def sweep_bias(self) -> Bias:
        return next(b for b in self.biases if b.role is BiasRole.SWEEP)

    def step_biases(self) -> list[Bias]:
        return [b for b in self.biases if b.role is BiasRole.STEP]

    def const_biases(self) -> list[Bias]:
        return [b for b in self.biases if b.role is BiasRole.CONST]

    def step_combinations(self) -> list[dict[str, float]]:
        """바깥 루프가 훑는 조합들. 없으면 빈 조합 하나."""
        steps = self.step_biases()
        if not steps:
            return [{}]
        return [
            dict(zip((b.name for b in steps), combination, strict=True))
            for combination in product(*(b.points() for b in steps))
        ]

    @model_validator(mode="after")
    def _consistent(self) -> DeviceSpec:
        labels = [electrode.label for electrode in self.electrodes]
        if len(labels) != len(set(labels)):
            raise ValueError("전극 이름이 겹칩니다")

        sweeps = [b for b in self.biases if b.role is BiasRole.SWEEP]
        if len(sweeps) != 1:
            raise ValueError("스윕 전압원은 정확히 하나여야 합니다")

        known = set(labels)
        claimed: dict[str, str] = {}
        for bias in self.biases:
            for label in bias.electrodes:
                if label not in known:
                    raise ValueError(f"{label!r} 라는 전극이 없습니다")
                if label in claimed:
                    raise ValueError(
                        f"전극 {label!r} 가 두 전압원({claimed[label]}, {bias.name})에"
                        " 걸려 있습니다"
                    )
                claimed[label] = bias.name

        loose = known - set(claimed)
        if loose:
            raise ValueError(
                f"전압원에 안 걸린 전극이 있습니다: {', '.join(sorted(loose))}"
            )

        if len(sweeps[0].points()) > MAX_SWEEP_POINTS:
            raise ValueError(f"스윕 점이 너무 많습니다(최대 {MAX_SWEEP_POINTS})")
        if total_points(self) > MAX_TOTAL_POINTS:
            raise ValueError(f"바이어스 점이 너무 많습니다(최대 {MAX_TOTAL_POINTS})")
        return self


def sweep_values(start: float, stop: float, step: float) -> list[float]:
    """양 끝을 포함하는 스윕 점.

    간격이 구간을 딱 나누지 않아도 마지막 점은 `stop` 이다. 스윕이 목표 전압에
    못 미치고 끝나면 그 지점의 값을 못 얻는다.
    """
    if step <= 0:
        raise ValueError("스윕 간격은 0 보다 커야 합니다")
    if start == stop:
        return [start]

    direction = 1.0 if stop > start else -1.0
    span = abs(stop - start)
    count = int(span / step)
    values = [start + direction * step * i for i in range(count + 1)]
    if abs(values[-1] - stop) > step * 1e-9:
        values.append(stop)
    else:
        values[-1] = stop
    return values


def total_points(spec: DeviceSpec) -> int:
    """풀어야 할 바이어스 점의 총수. 진행률의 분모이기도 하다."""
    return len(spec.sweep_bias().points()) * len(spec.step_combinations())
