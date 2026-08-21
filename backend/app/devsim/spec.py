"""해석 스펙과 그 검증.

브라우저에서 온 값이 그대로 솔버로 들어간다. 스펙 자체는 코드가 아니지만(우리가
쓴 고정 스크립트가 읽는다) 크기와 짜임새는 사용자가 정한다. 여기서 막지 않으면
바이어스 점 10만 개짜리 요청이 컨테이너 안에서 타임아웃까지 돌게 된다.

세 계층이 있고, 사용자가 손대는 것은 가운데 하나뿐이다.

    계면(interface)  **구조에서 나온다.** 금속 덩어리 하나, 뒷면 하나.
                     사용자가 만들거나 고칠 수 없다 — 반도체 표면 아무 데나
                     접촉을 걸 수 있게 하면 소자가 아니라 수치 실험이 된다.
    전극(electrode)  **사용자가 계면을 묶는다.** 이름을 붙이고, 단면에서 계면을
                     골라 붙인다. 한 계면은 한 전극에만 속한다.
    전압원(bias)     **전극마다 정확히 하나.** 역할(스윕/단계/고정)과 전압을
                     정한다. 여러 계면을 한 전위로 묶고 싶으면 전극 쪽에서
                     계면을 여러 개 붙이면 된다 — 전압원이 전극을 여러 개
                     거느리게 하면 같은 일을 두 군데서 할 수 있게 된다.
"""

from __future__ import annotations

from enum import Enum
from itertools import product
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


class ElectrodeChoice(BaseModel):
    """해석에 쓸 전극 하나. 계면 몇 개를 한 전위로 묶은 것이다.

    `interfaces` 는 자동으로 찾은 계면의 열쇠들이다(source/gate/drain/contactN/
    body). 같은 구조·같은 게이트 모델이면 늘 같게 나오므로 안정적인 이름이다.
    좌표를 받지 않는 이유: 스펙은 저장되고 다시 쓰이는데, 그 사이 다른 구조에
    붙으면 좌표가 안 맞는다. 이름만 받아 구조에서 다시 찾으면 안 맞을 때
    조용히 엉뚱한 자리를 잡는 대신 오류가 난다.
    """

    label: str = Field(min_length=1, max_length=32)
    interfaces: list[str] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def _no_repeats(self) -> ElectrodeChoice:
        if len(set(self.interfaces)) != len(self.interfaces):
            raise ValueError(f"{self.label}: 같은 계면이 여러 번 들어 있습니다")
        return self


class SweepRange(BaseModel):
    """스윕 구간. **점 개수**로 정한다.

    간격으로 정하면 `0 → 1` 을 `0.3` 씩 훑을 때 몇 점이 나오는지 손으로 세야
    하고, 끝점이 걸리는지 안 걸리는지도 눈에 안 보인다. 실행 시간은 점 개수에
    비례하므로, 사용자가 정하려는 것과 숫자가 일치한다.
    """

    start: float = Field(ge=-MAX_ABS_VOLTS, le=MAX_ABS_VOLTS)
    stop: float = Field(ge=-MAX_ABS_VOLTS, le=MAX_ABS_VOLTS)
    points: int = Field(gt=0)


class Bias(BaseModel):
    """전압원 하나. 전극 하나를 몰아준다.

    전극과 1:1 이다. 하나의 전압원이 전극을 여러 개 거느리게 하면 "여러 계면을
    한 전위로" 라는 같은 일을 전극 쪽과 전압원 쪽 두 군데서 할 수 있게 되고,
    화면에서는 그 두 길이 서로를 덮어쓴다.
    """

    name: str = Field(min_length=1, max_length=32)
    electrode: str = Field(min_length=1, max_length=32)
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
        return sweep_values(self.sweep.start, self.sweep.stop, self.sweep.points)


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
    #: 계면에 사용자가 붙인 이름. 열쇠는 그대로 두고 표시만 바꾼다 — 열쇠는
    #: 구조에서 나온 신원이라, 바꾸면 다음 실행에서 그 계면을 못 찾는다.
    interface_names: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sane_interface_names(self) -> DeviceSpec:
        if len(self.interface_names) > 32:
            raise ValueError("계면 이름이 너무 많습니다")
        for key, name in self.interface_names.items():
            if not key or len(key) > 32:
                raise ValueError(f"계면 열쇠가 이상합니다: {key!r}")
            if not name.strip() or len(name) > 32:
                raise ValueError(f"{key}: 계면 이름은 1~32 자여야 합니다")
        return self

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

    def bias_of(self, label: str) -> Bias:
        return next(bias for bias in self.biases if bias.electrode == label)

    @model_validator(mode="after")
    def _consistent(self) -> DeviceSpec:
        labels = [electrode.label for electrode in self.electrodes]
        if len(labels) != len(set(labels)):
            raise ValueError("전극 이름이 겹칩니다")

        # 한 계면은 한 전극에만 속한다. 두 전극이 같은 계면을 물면 같은 변에
        # 서로 다른 전위를 걸겠다는 뜻이 되고, 솔버가 무엇을 골랐는지 알 수 없다.
        owner: dict[str, str] = {}
        for electrode in self.electrodes:
            for key in electrode.interfaces:
                if key in owner:
                    raise ValueError(
                        f"계면 {key!r} 가 두 전극({owner[key]}, {electrode.label})에"
                        " 걸려 있습니다"
                    )
                owner[key] = electrode.label

        sweeps = [b for b in self.biases if b.role is BiasRole.SWEEP]
        if len(sweeps) != 1:
            raise ValueError("스윕 전압원은 정확히 하나여야 합니다")

        known = set(labels)
        driven: dict[str, str] = {}
        for bias in self.biases:
            if bias.electrode not in known:
                raise ValueError(f"{bias.electrode!r} 라는 전극이 없습니다")
            if bias.electrode in driven:
                raise ValueError(
                    f"전극 {bias.electrode!r} 에 전압원이 둘"
                    f"({driven[bias.electrode]}, {bias.name}) 붙어 있습니다"
                )
            driven[bias.electrode] = bias.name

        loose = known - set(driven)
        if loose:
            raise ValueError(
                f"전압원이 없는 전극이 있습니다: {', '.join(sorted(loose))}"
            )

        if len(sweeps[0].points()) > MAX_SWEEP_POINTS:
            raise ValueError(f"스윕 점이 너무 많습니다(최대 {MAX_SWEEP_POINTS})")
        if total_points(self) > MAX_TOTAL_POINTS:
            raise ValueError(f"바이어스 점이 너무 많습니다(최대 {MAX_TOTAL_POINTS})")
        return self


def sweep_values(start: float, stop: float, points: int) -> list[float]:
    """구간을 고르게 나눈 전압들. 양 끝을 반드시 포함한다.

    간격을 받던 시절에는 간격이 구간을 딱 나누지 않을 때 끝점을 따로 붙여야
    했고, 그래서 점 개수가 사용자가 센 것과 어긋났다. 개수를 받으면 그런 일이
    없다.
    """
    if points <= 0:
        return []
    if points == 1 or start == stop:
        return [start]
    span = stop - start
    return [start + span * index / (points - 1) for index in range(points)]


def total_points(spec: DeviceSpec) -> int:
    """풀어야 할 바이어스 점의 총수. 진행률의 분모이기도 하다."""
    return len(spec.sweep_bias().points()) * len(spec.step_combinations())
