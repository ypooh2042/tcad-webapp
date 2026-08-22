"""스펙 → 실제 전극 → 컨테이너 페이로드.

스펙은 전극을 **이름으로만** 가리킨다. 좌표와 변은 구조에서 다시 뽑아야 한다.
브라우저가 보낸 기하를 그대로 믿으면, 다른 구조에 붙은 스펙이 엉뚱한 자리를
전극이라고 우기게 된다.
"""

import json
from dataclasses import replace
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
            {"label": "S", "interfaces": ["source"]},
            {"label": "G", "interfaces": ["gate"]},
            {"label": "D", "interfaces": ["drain"]},
            {"label": "B", "interfaces": ["body"]},
        ],
        "biases": [
            {"name": "Vs", "electrode": "S", "role": "const", "value": 0.0},
            {"name": "Vb", "electrode": "B", "role": "const", "value": 0.0},
            {"name": "Vg", "electrode": "G", "role": "step", "values": [0.0, 1.0]},
            {
                "name": "Vd",
                "electrode": "D",
                "role": "sweep",
                "sweep": {"start": 0.0, "stop": 1.0, "points": 3},
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

    def test_keeps_the_geometry_of_the_interface(self, contacts, spec) -> None:
        found = {e.name: e for e in resolve_electrodes(contacts, spec)}
        assert found["G"].materials == ("poly",)
        assert found["S"].materials == ("silicon",)

    def test_unknown_interface_is_refused(self, contacts) -> None:
        payload = spec_payload()
        payload["electrodes"][0]["interfaces"] = ["collector"]
        with pytest.raises(ElectrodeNotFound, match="collector"):
            resolve_electrodes(contacts, DeviceSpec.model_validate(payload))

    def test_merges_the_edges_of_every_interface_it_holds(self, contacts) -> None:
        """여러 계면을 한 전극에 붙이면 변이 합쳐진다 — 그것이 등전위다."""
        single = {e.name: e for e in resolve_electrodes(
            contacts, DeviceSpec.model_validate(spec_payload())
        )}
        payload = spec_payload()
        payload["electrodes"][0]["interfaces"] = ["source", "body"]
        payload["electrodes"] = [e for e in payload["electrodes"] if e["label"] != "B"]
        payload["biases"] = [b for b in payload["biases"] if b["electrode"] != "B"]
        merged = {e.name: e for e in resolve_electrodes(
            contacts, DeviceSpec.model_validate(payload)
        )}
        assert len(merged["S"].edges) == len(single["S"].edges) + len(
            single["B"].edges
        )

    def test_an_electrode_may_be_left_out(self, contacts) -> None:
        payload = spec_payload()
        payload["electrodes"] = [
            e for e in payload["electrodes"] if e["label"] != "B"
        ]
        payload["biases"] = [b for b in payload["biases"] if b["electrode"] != "B"]
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
        # 전압원은 전극마다 하나다. 기판도 자기 전압원을 갖는다.
        assert by_name["D"]["bias"] == "Vd"
        assert by_name["S"]["bias"] == "Vs"
        assert by_name["B"]["bias"] == "Vb"

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
        assert payload["plan"]["constants"] == {"Vs": 0.0, "Vb": 0.0}


class TestDuplicateInterfaceKeys:
    """열쇠가 겹치면 조용히 넘어가지 않는다.

    `resolve_electrodes` 는 계면을 `{이름: 계면}` 으로 모은다. 이름이 겹치면
    뒤엣것이 앞엣것을 덮어써서 한쪽이 엉뚱한 자리에 걸린 채로 해석이 돌아간다 —
    오류 없이 틀린 곡선이 나오는 것보다 멈추는 편이 낫다.
    """

    def test_two_gates_become_two_electrodes(self) -> None:
        two = parse_structure((FIXTURES / "2d_two_gates.str").read_text())
        payload = spec_payload()
        payload["electrodes"] = [
            {"label": "G1", "interfaces": ["gate1"]},
            {"label": "G2", "interfaces": ["gate2"]},
            {"label": "B", "interfaces": ["body"]},
        ]
        payload["biases"] = [
            {"name": "V1", "electrode": "G1", "role": "const", "value": 0.0},
            {"name": "V2", "electrode": "G2", "role": "const", "value": 0.0},
            {
                "name": "Vb",
                "electrode": "B",
                "role": "sweep",
                "sweep": {"start": 0.0, "stop": 1.0, "points": 3},
            },
        ]
        found = {
            one.name: one
            for one in resolve_electrodes(two, DeviceSpec.model_validate(payload))
        }
        assert set(found) == {"G1", "G2", "B"}
        # 서로 다른 변을 물어야 한다. 겹치면 두 게이트가 같은 자리를 가리킨다.
        assert set(found["G1"].edges).isdisjoint(found["G2"].edges)

    def test_refuses_when_detection_gives_duplicate_keys(self, contacts) -> None:
        from unittest.mock import patch

        from app.devsim.electrodes import detect_interfaces

        doubled = detect_interfaces(contacts)
        clashing = (*doubled, replace(doubled[0], edges=doubled[1].edges))
        with patch("app.devsim.resolve.detect_interfaces", return_value=clashing):
            with pytest.raises(ElectrodeNotFound, match="겹칩니다"):
                resolve_electrodes(
                    contacts, DeviceSpec.model_validate(spec_payload())
                )


class TestEmptyElectrode:
    """계면이 안 붙은 전극은 **여기서** 걸린다.

    파싱(`DeviceSpec`)은 그것을 통과시킨다 — "전극 추가" 를 누른 직후가 그
    상태이고, 거기서 막으면 편집 도중의 조건을 맡아 둘 수 없어 사용자가 저장한
    줄 알고 새로고침했다가 잃는다. 대신 해석을 돌리기 직전인 이 자리에서 막는다.
    잡 제출과 워커가 둘 다 여기를 거치므로 빈 전극으로 해석이 도는 일은 없다.
    """

    def test_refuses_to_resolve(self, contacts) -> None:
        payload = spec_payload()
        payload["electrodes"].append({"label": "새 전극", "interfaces": []})
        payload["biases"].append(
            {"name": "V새", "electrode": "새 전극", "role": "const", "value": 0.0}
        )
        spec = DeviceSpec.model_validate(payload)

        with pytest.raises(ElectrodeNotFound, match="접촉 변"):
            resolve_electrodes(contacts, spec)

    def test_names_the_electrode_that_is_empty(self, contacts) -> None:
        # 전극이 여럿일 때 어느 것인지 말해 주지 않으면 찾아다녀야 한다.
        payload = spec_payload()
        payload["electrodes"].append({"label": "새 전극", "interfaces": []})
        payload["biases"].append(
            {"name": "V새", "electrode": "새 전극", "role": "const", "value": 0.0}
        )
        spec = DeviceSpec.model_validate(payload)

        with pytest.raises(ElectrodeNotFound, match="새 전극"):
            resolve_electrodes(contacts, spec)

    def test_restorable_lets_it_through(self, contacts) -> None:
        """저장·복원 쪽은 통과시킨다. 묻는 것이 다르다."""
        from app.devsim.resolve import restorable

        payload = spec_payload()
        payload["electrodes"].append({"label": "새 전극", "interfaces": []})
        payload["biases"].append(
            {"name": "V새", "electrode": "새 전극", "role": "const", "value": 0.0}
        )
        spec = DeviceSpec.model_validate(payload)

        restorable(contacts, spec)  # 예외가 나지 않아야 한다

    def test_restorable_still_catches_a_missing_interface(self, contacts) -> None:
        from app.devsim.resolve import restorable

        payload = spec_payload()
        payload["electrodes"][0]["interfaces"] = ["그런계면없음"]
        spec = DeviceSpec.model_validate(payload)

        with pytest.raises(ElectrodeNotFound, match="그런계면없음"):
            restorable(contacts, spec)


class TestFloatingInThePlan:
    """부유 전압원은 컨테이너가 **회로 노드**로 만들어야 한다.

    그러려면 어느 전압원이 부유인지 페이로드에 실려야 한다. 접촉에는 이미
    `"bias"` 가 있어 소속을 알 수 있으므로, 이름 목록 하나만 더하면 된다.
    """

    def _floating(self, label: str = "B"):
        payload = spec_payload()
        for bias in payload["biases"]:
            if bias["electrode"] == label:
                bias["role"] = "float"
                bias.pop("value", None)
        return payload

    def test_the_plan_names_the_floating_sources(self, contacts) -> None:
        spec = DeviceSpec.model_validate(self._floating())

        built = build_payload(contacts, spec)

        assert built["plan"]["floating"] == ["Vb"]

    def test_no_floating_means_an_empty_list(self, contacts) -> None:
        """키는 늘 있어야 한다. 없을 때만 다르게 읽으면 컨테이너가 갈린다."""
        spec = DeviceSpec.model_validate(spec_payload())

        built = build_payload(contacts, spec)

        assert built["plan"]["floating"] == []

    def test_a_floating_source_is_not_a_constant(self, contacts) -> None:
        """부유는 걸어 줄 전압이 없다. constants 에 섞이면 0 V 로 구동된다."""
        spec = DeviceSpec.model_validate(self._floating())

        built = build_payload(contacts, spec)

        assert "Vb" not in built["plan"]["constants"]

    def test_its_contacts_still_carry_the_bias_name(self, contacts) -> None:
        """접촉이 어느 회로 노드에 붙는지 이 이름으로 안다."""
        spec = DeviceSpec.model_validate(self._floating())

        built = build_payload(contacts, spec)

        floating = [c for c in built["contacts"] if c["bias"] == "Vb"]
        assert floating, built["contacts"]

    def test_the_point_count_ignores_floating(self, contacts) -> None:
        spec = DeviceSpec.model_validate(self._floating())

        built = build_payload(contacts, spec)

        assert built["plan"]["total"] == 3 * 2  # 스윕 3점 × 단계 2개
