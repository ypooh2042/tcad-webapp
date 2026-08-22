"""해석 스펙 검증 테스트.

스펙은 브라우저에서 온다. 컨테이너 안에서 도는 스크립트는 우리가 쓴 고정
스크립트지만, 그 스크립트가 읽는 값은 사용자 입력이다. 여기서 막지 못한 것은
그대로 솔버로 들어간다 — 바이어스 점 10만 개짜리 요청 같은 것.
"""

import pytest
from pydantic import ValidationError

from app.devsim.spec import (
    MAX_TOTAL_POINTS,
    BiasRole,
    DeviceSpec,
    sweep_values,
    total_points,
)


def build(**overrides) -> dict:
    payload = {
        "electrodes": [
            {"label": "source", "interfaces": ["source"]},
            {"label": "gate", "interfaces": ["gate"]},
            {"label": "drain", "interfaces": ["drain"]},
            {"label": "body", "interfaces": ["body"]},
        ],
        "biases": [
            {"name": "Vs", "electrode": "source", "role": "const", "value": 0.0},
            {"name": "Vb", "electrode": "body", "role": "const", "value": 0.0},
            {"name": "Vg", "electrode": "gate", "role": "step", "values": [0.0, 1.0]},
            {
                "name": "Vd",
                "electrode": "drain",
                "role": "sweep",
                "sweep": {"start": 0.0, "stop": 2.0, "points": 5},
            },
        ],
    }
    payload.update(overrides)
    return payload


class TestSweepValues:
    """스윕은 **점 개수**로 정한다.

    간격으로 정하면 `0 → 1` 을 `0.3` 씩 훑을 때 몇 점이 나오는지 손으로 세야
    하고, 끝점이 걸리는지 안 걸리는지도 눈에 안 보인다. 점 개수로 정하면 실행
    시간이 곧 그 숫자에 비례하므로 사용자가 정하려는 것과 일치한다.
    """

    def test_spreads_the_points_evenly(self) -> None:
        assert sweep_values(0.0, 2.0, 5) == [0.0, 0.5, 1.0, 1.5, 2.0]

    def test_always_hits_both_ends(self) -> None:
        values = sweep_values(0.0, 1.0, 4)
        assert values[0] == 0.0
        assert values[-1] == 1.0

    def test_walks_downward_too(self) -> None:
        assert sweep_values(1.0, 0.0, 3) == [1.0, 0.5, 0.0]

    def test_one_point_sits_at_the_start(self) -> None:
        assert sweep_values(0.5, 2.0, 1) == [0.5]

    def test_no_points_is_nothing(self) -> None:
        assert sweep_values(0.0, 1.0, 0) == []

    def test_same_start_and_stop_repeats_nothing(self) -> None:
        assert sweep_values(1.0, 1.0, 3) == [1.0]


class TestValidSpec:
    def test_accepts_a_normal_mosfet_setup(self) -> None:
        spec = DeviceSpec.model_validate(build())
        assert len(spec.electrodes) == 4
        assert spec.sweep_bias().name == "Vd"
        assert [b.name for b in spec.step_biases()] == ["Vg"]

    def test_every_electrode_has_exactly_one_source(self) -> None:
        spec = DeviceSpec.model_validate(build())
        for electrode in spec.electrodes:
            assert spec.bias_of(electrode.label).electrode == electrode.label

    def test_an_electrode_can_hold_several_interfaces(self) -> None:
        """여러 계면을 한 전위로 묶는 길은 전극 쪽 하나뿐이다."""
        payload = build()
        payload["electrodes"][0]["interfaces"] = ["source", "body"]
        payload["electrodes"] = [
            e for e in payload["electrodes"] if e["label"] != "body"
        ]
        payload["biases"] = [b for b in payload["biases"] if b["electrode"] != "body"]
        spec = DeviceSpec.model_validate(payload)
        assert spec.electrodes[0].interfaces == ["source", "body"]

    def test_counts_the_bias_points(self) -> None:
        spec = DeviceSpec.model_validate(build())
        # 스윕 5점 × 게이트 2단계
        assert total_points(spec) == 10

    def test_defaults_to_the_semiconductor_gate_model(self) -> None:
        spec = DeviceSpec.model_validate(build())
        assert spec.gate_model.value == "semiconductor"


class TestRejections:
    def test_needs_exactly_one_sweep(self) -> None:
        payload = build()
        payload["biases"][2]["role"] = "sweep"
        payload["biases"][2]["sweep"] = {"start": 0.0, "stop": 1.0, "points": 3}
        with pytest.raises(ValidationError, match="스윕"):
            DeviceSpec.model_validate(payload)

    def test_rejects_no_sweep_at_all(self) -> None:
        payload = build()
        payload["biases"][3]["role"] = "const"
        payload["biases"][3]["value"] = 1.0
        with pytest.raises(ValidationError, match="스윕"):
            DeviceSpec.model_validate(payload)

    def test_rejects_two_sources_on_one_electrode(self) -> None:
        # 전압원과 전극은 1:1 이다. 둘이 붙으면 어느 전위가 걸리는지 알 수 없다.
        payload = build()
        payload["biases"][1]["electrode"] = "source"
        with pytest.raises(ValidationError, match="전압원이 둘"):
            DeviceSpec.model_validate(payload)

    def test_rejects_an_unknown_electrode(self) -> None:
        payload = build()
        payload["biases"][0]["electrode"] = "substrate"
        with pytest.raises(ValidationError, match="전극"):
            DeviceSpec.model_validate(payload)

    def test_rejects_an_interface_claimed_by_two_electrodes(self) -> None:
        """한 계면에 두 전위를 걸 수는 없다."""
        payload = build()
        payload["electrodes"][3]["interfaces"] = ["body", "source"]
        with pytest.raises(ValidationError, match="두 전극"):
            DeviceSpec.model_validate(payload)

    def test_rejects_the_same_interface_twice_in_one_electrode(self) -> None:
        payload = build()
        payload["electrodes"][0]["interfaces"] = ["source", "source"]
        with pytest.raises(ValidationError, match="여러 번"):
            DeviceSpec.model_validate(payload)

    def test_accepts_an_electrode_with_no_interface_yet(self) -> None:
        """계면이 없는 전극은 **파싱에서 막지 않는다.**

        "전극 추가" 를 누른 직후가 그 상태다. 여기서 막으면 편집 도중의 조건을
        아예 맡아 둘 수 없어(422), 사용자는 저장된 줄 알고 새로고침했다가 그
        전에 해 둔 것까지 잃는다.

        걸 데가 없다는 판단 자체는 옳다 — 다만 그것은 **해석을 돌릴 때** 할 일이라
        `resolve_electrodes` 로 옮겼다. 아래 시험이 그쪽을 지킨다.
        """
        payload = build()
        payload["electrodes"][0]["interfaces"] = []

        spec = DeviceSpec.model_validate(payload)

        assert spec.electrodes[0].interfaces == []

    def test_rejects_duplicate_electrode_labels(self) -> None:
        payload = build()
        payload["electrodes"][1]["label"] = "source"
        with pytest.raises(ValidationError, match="이름"):
            DeviceSpec.model_validate(payload)

    def test_rejects_an_electrode_with_no_source(self) -> None:
        payload = build()
        payload["biases"] = payload["biases"][1:]
        with pytest.raises(ValidationError, match="전압원이 없는"):
            DeviceSpec.model_validate(payload)

    def test_rejects_zero_points(self) -> None:
        payload = build()
        payload["biases"][3]["sweep"]["points"] = 0
        with pytest.raises(ValidationError):
            DeviceSpec.model_validate(payload)

    def test_rejects_too_many_points_in_total(self) -> None:
        """축마다는 멀쩡해도 곱이 크면 거절한다. 곡선족이 그렇게 커진다."""
        payload = build()
        payload["biases"][2]["values"] = [float(v) for v in range(16)]
        payload["biases"][3]["sweep"] = {"start": 0.0, "stop": 50.0, "points": 101}
        with pytest.raises(ValidationError, match="바이어스 점"):
            DeviceSpec.model_validate(payload)

    def test_rejects_too_many_points_on_one_axis(self) -> None:
        payload = build()
        payload["biases"][2]["values"] = [0.0]
        payload["biases"][3]["sweep"] = {"start": 0.0, "stop": 100.0, "points": 5000}
        with pytest.raises(ValidationError, match="스윕 점"):
            DeviceSpec.model_validate(payload)

    def test_the_cap_is_reachable_but_not_exceeded(self) -> None:
        payload = build()
        payload["biases"][2]["values"] = [0.0, 1.0]
        # 단계 2 개이므로 스윕을 상한의 절반만큼 놓으면 총수가 딱 상한이 된다.
        half = MAX_TOTAL_POINTS // 2
        payload["biases"][3]["sweep"] = {
            "start": 0.0,
            "stop": 10.0,
            "points": half,
        }
        spec = DeviceSpec.model_validate(payload)
        assert total_points(spec) == MAX_TOTAL_POINTS

    def test_const_needs_a_value(self) -> None:
        payload = build()
        del payload["biases"][0]["value"]
        with pytest.raises(ValidationError):
            DeviceSpec.model_validate(payload)

    def test_step_needs_values(self) -> None:
        payload = build()
        payload["biases"][2]["values"] = []
        with pytest.raises(ValidationError):
            DeviceSpec.model_validate(payload)

    def test_rejects_absurd_bias_values(self) -> None:
        payload = build()
        payload["biases"][0]["value"] = 1.0e6
        with pytest.raises(ValidationError):
            DeviceSpec.model_validate(payload)


class TestRoles:
    def test_role_names_match_the_wire_format(self) -> None:
        assert BiasRole.SWEEP.value == "sweep"
        assert BiasRole.STEP.value == "step"
        assert BiasRole.CONST.value == "const"

    def test_a_source_without_an_electrode_is_refused(self) -> None:
        payload = build()
        payload["biases"].append(
            {"name": "Vx", "electrode": "", "role": "const", "value": 0.0}
        )
        with pytest.raises(ValidationError):
            DeviceSpec.model_validate(payload)


class TestFloatingBias:
    """출력 노드는 전압을 **주는** 것이 아니라 **풀어서 얻는** 것이다.

    CMOS 인버터의 출력 전위는 회로가 스스로 정한다. 지금처럼 21 개 전압에
    강제로 묶고 전류가 0 인 지점을 사람이 찾는 방식은, 입력 하나당 21 번 풀어
    20 번을 버리는 셈이다. 게다가 자연 동작점에서 멀수록 큰 전류가 흘러
    (실측 −440 µA/µm) 수치적으로도 어렵다.

    부유를 **역할**로 둔 이유: 전압원은 여전히 전극에 1:1 로 붙어 있고 값만
    없다. 그래서 "전극마다 전압원 하나" 를 강제하는 기존 검증과 화면 구조가
    그대로 산다.
    """

    def test_a_floating_bias_needs_no_voltage(self) -> None:
        payload = build()
        payload["biases"][0]["role"] = "float"
        payload["biases"][0].pop("value", None)

        spec = DeviceSpec.model_validate(payload)

        assert spec.biases[0].role is BiasRole.FLOAT

    def test_a_floating_bias_must_not_carry_one(self) -> None:
        """값을 함께 주면 무엇을 하겠다는 것인지 알 수 없다."""
        payload = build()
        payload["biases"][0]["role"] = "float"
        payload["biases"][0]["value"] = 1.0

        with pytest.raises(ValidationError, match="부유"):
            DeviceSpec.model_validate(payload)

    def test_all_floating_is_rejected(self) -> None:
        """전부 부유면 기준 전위가 없다 — 전압은 늘 어딘가에 대한 차이다.

        따로 검사하지 않는다. **스윕 전압원이 필수이고 스윕은 언제나 구동**
        이므로 기존 규칙이 이미 막는다. 죽은 검증을 더하지 않으려고 이 시험이
        그 사실을 붙들어 둔다 — 스윕 필수 규칙이 사라지면 여기서 드러난다.
        """
        payload = build()
        for bias in payload["biases"]:
            bias["role"] = "float"
            bias.pop("value", None)
            bias.pop("values", None)
            bias.pop("sweep", None)

        with pytest.raises(ValidationError, match="스윕"):
            DeviceSpec.model_validate(payload)

    def test_the_electrode_still_has_a_source(self) -> None:
        """부유도 전압원이다. 그래서 '전압원 없는 전극' 규칙이 안 깨진다."""
        payload = build()
        payload["biases"][0]["role"] = "float"
        payload["biases"][0].pop("value", None)

        spec = DeviceSpec.model_validate(payload)

        attached = {bias.electrode for bias in spec.biases}
        assert attached == {e.label for e in spec.electrodes}

    def test_a_floating_bias_walks_no_points(self) -> None:
        """부유 전압원은 훑을 전압이 없다. 점 수에 기여하면 안 된다."""
        payload = build()
        payload["biases"][0]["role"] = "float"
        payload["biases"][0].pop("value", None)
        spec = DeviceSpec.model_validate(payload)

        assert spec.biases[0].points() == []

    def test_floating_biases_are_listed(self) -> None:
        payload = build()
        payload["biases"][0]["role"] = "float"
        payload["biases"][0].pop("value", None)
        spec = DeviceSpec.model_validate(payload)

        assert [b.name for b in spec.floating_biases()] == [
            payload["biases"][0]["name"]
        ]


class TestSweepFromAList:
    """스윕 전압을 **직접 적을 수 있어야 한다.**

    등간격만 되면 어려운 구간에 점을 몰아줄 수 없다. 인버터 전달특성이 딱
    그런 경우다 — 전환 구간에서만 출력이 급변하는데, 거기 촘촘히 잡으려고
    전 구간을 촘촘히 하면 쉬운 구간에서 시간을 버린다. 실측에서 0.5 V 간격이
    전환 구간을 못 넘어 3 점을 잃었다.

    단계 전압원이 이미 목록을 받으므로 같은 자리(`values`)를 쓴다 — 뜻도 같다
    ("이 전압원이 훑는 전압들").
    """

    def _listed(self, values):
        payload = build()
        for bias in payload["biases"]:
            if bias["role"] == "sweep":
                bias.pop("sweep", None)
                bias["values"] = values
        return payload

    def test_a_sweep_can_carry_a_list(self) -> None:
        spec = DeviceSpec.model_validate(self._listed([0.0, 1.0, 1.5, 1.75, 2.0, 5.0]))

        assert spec.sweep_bias().points() == [0.0, 1.0, 1.5, 1.75, 2.0, 5.0]

    def test_the_order_is_kept(self) -> None:
        """적은 순서대로 걷는다. 직류에는 이력이 없어 답은 같지만, 어느 쪽에서
        접근하느냐가 수렴을 가르므로 사용자가 정할 수 있어야 한다."""
        spec = DeviceSpec.model_validate(self._listed([5.0, 2.0, 0.0]))

        assert spec.sweep_bias().points() == [5.0, 2.0, 0.0]

    def test_equal_spacing_still_works(self) -> None:
        spec = DeviceSpec.model_validate(build())

        assert len(spec.sweep_bias().points()) > 1

    def test_a_sweep_needs_one_or_the_other(self) -> None:
        payload = build()
        for bias in payload["biases"]:
            if bias["role"] == "sweep":
                bias.pop("sweep", None)

        with pytest.raises(ValidationError, match="스윕"):
            DeviceSpec.model_validate(payload)

    def test_both_at_once_is_refused(self) -> None:
        """둘 다 주면 어느 쪽을 쓰겠다는 것인지 알 수 없다."""
        payload = build()
        for bias in payload["biases"]:
            if bias["role"] == "sweep":
                bias["values"] = [0.0, 1.0]

        with pytest.raises(ValidationError, match="둘 중 하나"):
            DeviceSpec.model_validate(payload)

    def test_a_long_list_is_allowed_for_a_sweep(self) -> None:
        """단계는 16 개까지지만 스윕은 곡선의 x 축이라 훨씬 많이 필요하다."""
        spec = DeviceSpec.model_validate(self._listed([i * 0.1 for i in range(40)]))

        assert len(spec.sweep_bias().points()) == 40

    def test_a_step_source_is_still_capped(self) -> None:
        payload = build()
        for bias in payload["biases"]:
            if bias["role"] == "step":
                bias["values"] = [float(i) for i in range(20)]

        with pytest.raises(ValidationError, match="단계"):
            DeviceSpec.model_validate(payload)
