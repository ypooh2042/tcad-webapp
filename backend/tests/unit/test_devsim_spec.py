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
            {"origin": "detected", "key": "source", "label": "source"},
            {"origin": "detected", "key": "gate", "label": "gate"},
            {"origin": "detected", "key": "drain", "label": "drain"},
            {"origin": "backside", "label": "body"},
        ],
        "biases": [
            {"name": "Vs", "electrodes": ["source", "body"], "role": "const", "value": 0.0},
            {"name": "Vg", "electrodes": ["gate"], "role": "step", "values": [0.0, 1.0]},
            {
                "name": "Vd",
                "electrodes": ["drain"],
                "role": "sweep",
                "sweep": {"start": 0.0, "stop": 2.0, "step": 0.5},
            },
        ],
    }
    payload.update(overrides)
    return payload


class TestSweepValues:
    def test_includes_both_ends(self) -> None:
        assert sweep_values(0.0, 2.0, 0.5) == [0.0, 0.5, 1.0, 1.5, 2.0]

    def test_walks_downward_too(self) -> None:
        assert sweep_values(1.0, 0.0, 0.5) == [1.0, 0.5, 0.0]

    def test_stops_at_the_end_even_when_the_step_does_not_divide(self) -> None:
        values = sweep_values(0.0, 1.0, 0.3)
        assert values[0] == 0.0
        assert values[-1] == pytest.approx(1.0)

    def test_single_point_when_start_equals_stop(self) -> None:
        assert sweep_values(1.0, 1.0, 0.5) == [1.0]


class TestValidSpec:
    def test_accepts_a_normal_mosfet_setup(self) -> None:
        spec = DeviceSpec.model_validate(build())
        assert len(spec.electrodes) == 4
        assert spec.sweep_bias().name == "Vd"
        assert [b.name for b in spec.step_biases()] == ["Vg"]

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
        payload["biases"][1]["role"] = "sweep"
        payload["biases"][1]["sweep"] = {"start": 0.0, "stop": 1.0, "step": 0.5}
        with pytest.raises(ValidationError, match="스윕"):
            DeviceSpec.model_validate(payload)

    def test_rejects_no_sweep_at_all(self) -> None:
        payload = build()
        payload["biases"][2]["role"] = "const"
        payload["biases"][2]["value"] = 1.0
        with pytest.raises(ValidationError, match="스윕"):
            DeviceSpec.model_validate(payload)

    def test_rejects_an_electrode_used_by_two_sources(self) -> None:
        payload = build()
        payload["biases"][0]["electrodes"] = ["source", "body", "drain"]
        with pytest.raises(ValidationError, match="두 전압원"):
            DeviceSpec.model_validate(payload)

    def test_rejects_an_unknown_electrode(self) -> None:
        payload = build()
        payload["biases"][0]["electrodes"] = ["substrate"]
        with pytest.raises(ValidationError, match="전극"):
            DeviceSpec.model_validate(payload)

    def test_rejects_duplicate_electrode_labels(self) -> None:
        payload = build()
        payload["electrodes"][1]["label"] = "source"
        with pytest.raises(ValidationError, match="이름"):
            DeviceSpec.model_validate(payload)

    def test_rejects_an_electrode_left_unconnected(self) -> None:
        payload = build()
        payload["biases"][0]["electrodes"] = ["source"]
        with pytest.raises(ValidationError, match="전압원"):
            DeviceSpec.model_validate(payload)

    def test_rejects_a_zero_step(self) -> None:
        payload = build()
        payload["biases"][2]["sweep"]["step"] = 0.0
        with pytest.raises(ValidationError):
            DeviceSpec.model_validate(payload)

    def test_rejects_too_many_points_in_total(self) -> None:
        """축마다는 멀쩡해도 곱이 크면 거절한다. 곡선족이 그렇게 커진다."""
        payload = build()
        payload["biases"][1]["values"] = [float(v) for v in range(16)]
        payload["biases"][2]["sweep"] = {"start": 0.0, "stop": 50.0, "step": 0.5}
        with pytest.raises(ValidationError, match="바이어스 점"):
            DeviceSpec.model_validate(payload)

    def test_rejects_too_many_points_on_one_axis(self) -> None:
        payload = build()
        payload["biases"][1]["values"] = [0.0]
        payload["biases"][2]["sweep"] = {"start": 0.0, "stop": 100.0, "step": 0.001}
        with pytest.raises(ValidationError, match="스윕 점"):
            DeviceSpec.model_validate(payload)

    def test_the_cap_is_reachable_but_not_exceeded(self) -> None:
        payload = build()
        payload["biases"][1]["values"] = [0.0, 1.0]
        # 단계 2 개이므로 스윕을 상한의 절반만큼 놓으면 총수가 딱 상한이 된다.
        half = MAX_TOTAL_POINTS // 2
        payload["biases"][2]["sweep"] = {
            "start": 0.0,
            "stop": (half - 1) * 0.5,
            "step": 0.5,
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
        payload["biases"][1]["values"] = []
        with pytest.raises(ValidationError):
            DeviceSpec.model_validate(payload)

    def test_picked_electrode_needs_a_box(self) -> None:
        payload = build()
        payload["electrodes"].append({"origin": "picked", "label": "extra"})
        with pytest.raises(ValidationError):
            DeviceSpec.model_validate(payload)

    def test_detected_electrode_needs_a_key(self) -> None:
        payload = build()
        payload["electrodes"][0] = {"origin": "detected", "label": "source"}
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

    def test_step_combinations_are_the_cartesian_product(self) -> None:
        payload = build()
        payload["biases"].append(
            {"name": "Vb", "electrodes": [], "role": "step", "values": [0.0, -1.0]}
        )
        # 전극이 없는 전압원은 거부돼야 한다.
        with pytest.raises(ValidationError):
            DeviceSpec.model_validate(payload)
