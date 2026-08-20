"""스펙 → 실제 전극 → 컨테이너 페이로드.

스펙은 전극을 **이름으로만** 가리킨다. 좌표와 변은 구조에서 다시 뽑아야 한다.
브라우저가 보낸 기하를 그대로 믿으면, 다른 구조에 붙은 스펙이 엉뚱한 자리를
전극이라고 우기게 된다.
"""

import json
from pathlib import Path

import pytest

from app.devsim.payload import build_payload
from app.devsim.resolve import ElectrodeNotFound, resolve_electrodes
from app.devsim.spec import DeviceSpec
from app.str_parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def contacts():
    return parse_structure((FIXTURES / "2d_contacts.str").read_text())


def spec_payload(**overrides) -> dict:
    payload = {
        "electrodes": [
            {"origin": "detected", "key": "source", "label": "S"},
            {"origin": "detected", "key": "gate", "label": "G"},
            {"origin": "detected", "key": "drain", "label": "D"},
            {"origin": "backside", "label": "B"},
        ],
        "biases": [
            {"name": "Vs", "electrodes": ["S", "B"], "role": "const", "value": 0.0},
            {"name": "Vg", "electrodes": ["G"], "role": "step", "values": [0.0, 1.0]},
            {
                "name": "Vd",
                "electrodes": ["D"],
                "role": "sweep",
                "sweep": {"start": 0.0, "stop": 1.0, "step": 0.5},
            },
        ],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def spec():
    return DeviceSpec.model_validate(spec_payload())


class TestResolve:
    def test_renames_to_the_users_labels(self, contacts, spec) -> None:
        found = resolve_electrodes(contacts, spec)
        assert sorted(e.name for e in found) == ["B", "D", "G", "S"]

    def test_keeps_the_geometry_of_the_detected_electrode(self, contacts, spec) -> None:
        found = {e.name: e for e in resolve_electrodes(contacts, spec)}
        assert found["G"].materials == ("poly",)
        assert found["S"].materials == ("silicon",)

    def test_unknown_key_is_refused(self, contacts) -> None:
        payload = spec_payload()
        payload["electrodes"][0]["key"] = "collector"
        with pytest.raises(ElectrodeNotFound, match="collector"):
            resolve_electrodes(contacts, DeviceSpec.model_validate(payload))

    def test_picked_box_selects_boundary_edges(self, contacts) -> None:
        depth = max(c.y for c in contacts.coordinates)
        payload = spec_payload()
        payload["electrodes"][3] = {
            "origin": "picked",
            "label": "B",
            "box": {
                "x_min": -0.1,
                "x_max": 1.0,
                "y_min": depth - 0.01,
                "y_max": depth + 0.01,
            },
        }
        found = {e.name: e for e in resolve_electrodes(
            contacts, DeviceSpec.model_validate(payload)
        )}
        body = found["B"]
        assert body.edges
        # 상자가 왼쪽 절반만 덮었으므로 뒷면 전체보다 좁아야 한다.
        assert body.extent.x_max <= 1.0

    def test_empty_box_is_refused(self, contacts) -> None:
        payload = spec_payload()
        payload["electrodes"][3] = {
            "origin": "picked",
            "label": "B",
            "box": {"x_min": 9.0, "x_max": 9.1, "y_min": 9.0, "y_max": 9.1},
        }
        with pytest.raises(ElectrodeNotFound, match="B"):
            resolve_electrodes(contacts, DeviceSpec.model_validate(payload))

    def test_missing_backside_is_refused(self, contacts) -> None:
        """뒷면 경계가 없는 구조에 backside 전극을 걸면 조용히 넘어가면 안 된다."""
        payload = spec_payload()
        payload["electrodes"] = [
            e for e in payload["electrodes"] if e["label"] != "B"
        ]
        payload["biases"][0]["electrodes"] = ["S"]
        spec = DeviceSpec.model_validate(payload)
        assert len(resolve_electrodes(contacts, spec)) == 3


class TestPayload:
    @pytest.fixture
    def payload(self, contacts, spec):
        return build_payload(contacts, spec)

    def test_is_json_serialisable(self, payload) -> None:
        # 컨테이너로는 파일로만 건너간다. 직렬화가 안 되면 거기서 죽는다.
        assert json.loads(json.dumps(payload))

    def test_carries_the_mesh_arrays(self, payload) -> None:
        mesh = payload["mesh"]
        assert len(mesh["coordinates"]) % 3 == 0
        assert mesh["elements"]
        assert mesh["physical_names"]

    def test_lists_contacts_with_their_bias_source(self, payload) -> None:
        by_name = {c["name"]: c for c in payload["contacts"]}
        assert set(by_name) == {"S", "G", "D", "B"}
        assert by_name["D"]["bias"] == "Vd"
        assert by_name["S"]["bias"] == "Vs"
        assert by_name["B"]["bias"] == "Vs"

    def test_doping_is_given_for_semiconductor_regions_only(self, payload) -> None:
        semiconductors = {
            r["name"] for r in payload["regions"] if r["is_semiconductor"]
        }
        assert set(payload["doping"]) == semiconductors
        assert semiconductors

    def test_doping_points_are_in_device_coordinates(self, payload) -> None:
        for points in payload["doping"].values():
            for x, y, _value in points:
                # cm 계. µm 그대로면 1e-4 배 크다.
                assert abs(x) < 1.0
                assert abs(y) < 1.0

    def test_every_semiconductor_node_has_a_doping_value(self, payload) -> None:
        names = {r["name"] for r in payload["regions"] if r["is_semiconductor"]}
        for name in names:
            assert payload["doping"][name]

    def test_carries_the_sweep_plan(self, payload) -> None:
        plan = payload["plan"]
        assert plan["sweep"]["bias"] == "Vd"
        assert plan["sweep"]["values"] == [0.0, 0.5, 1.0]
        assert plan["steps"] == [{"Vg": 0.0}, {"Vg": 1.0}]
        assert plan["total"] == 6

    def test_constant_biases_are_listed(self, payload) -> None:
        assert payload["plan"]["constants"] == {"Vs": 0.0}
