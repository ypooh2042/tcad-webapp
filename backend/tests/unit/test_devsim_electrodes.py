"""전극 추출 테스트.

판정 규칙은 발명한 것이 아니라 SUPREM 원본의 것을 그대로 옮긴 것이다.
`SUPREM4GS/upstream/src/include/device.h:35`:

    a contact is a semiconductor material touching an Exposed or backside
    or anything touching aluminum

그리고 `device/contact.c:104 gen_contact()` 가 연결된 접촉 변을 flood-fill 해서
하나의 contact 으로 묶는다. "같은 알루미늄 덩어리는 같은 전위"가 정확히 이것이다.

픽스처 `2d_contacts.str` 은 `2d_contacts.in` 을 실제로 돌려 만든 것이다. 알루미늄
플러그 셋이 각각 silicon(x 0.2~0.5), poly(x 0.85~1.15), silicon(x 1.5~1.8) 에
닿는다 — 즉 소스·게이트·드레인이다.
"""

from pathlib import Path

import pytest

from app.devsim.electrodes import (
    ContactKind,
    GateModel,
    backside_candidate,
    conductor_clusters,
    detect_electrodes,
)
from app.str_parser import parse_structure

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def contacts():
    return parse_structure((FIXTURES / "2d_contacts.str").read_text())


@pytest.fixture
def cmos_2d():
    """알루미늄이 없는 구조. 금속 이전 단계에서 전극이 안 잡혀야 한다."""
    return parse_structure((FIXTURES / "2d_cmos_source.str").read_text())


class TestConductorClusters:
    def test_finds_three_separate_plugs(self, contacts) -> None:
        clusters = conductor_clusters(contacts, {"aluminum"})
        assert len(clusters) == 3

    def test_every_aluminum_element_lands_in_exactly_one_cluster(
        self, contacts
    ) -> None:
        # 묶음은 요소 **인덱스**다. 이웃 번호가 인덱스라서 그쪽에 맞춰져 있다.
        materials = {r.id: r.material for r in contacts.regions}
        aluminum = {
            index
            for index, element in enumerate(contacts.elements)
            if materials[element.region_id] == "aluminum"
        }
        clusters = conductor_clusters(contacts, {"aluminum"})
        merged: set[int] = set()
        for cluster in clusters:
            assert not (merged & set(cluster)), "덩어리가 겹친다"
            merged |= set(cluster)
        assert merged == aluminum

    def test_no_aluminum_means_no_clusters(self, cmos_2d) -> None:
        assert conductor_clusters(cmos_2d, {"aluminum"}) == ()

    def test_including_poly_merges_the_gate_stack(self, contacts) -> None:
        """도체 집합에 poly 를 넣으면 게이트 플러그와 poly 가 한 덩어리가 된다.

        `gate_model='conductor'` 일 때의 동작이다. 덩어리 수는 그대로 셋이지만
        게이트 덩어리가 더 커진다.
        """
        with_poly = conductor_clusters(contacts, {"aluminum", "poly"})
        without = conductor_clusters(contacts, {"aluminum"})
        assert len(with_poly) == 3
        assert max(len(c) for c in with_poly) >= max(len(c) for c in without)
        assert sum(len(c) for c in with_poly) > sum(len(c) for c in without)


class TestDetectElectrodes:
    def test_finds_source_gate_drain(self, contacts) -> None:
        found = detect_electrodes(contacts)
        assert [e.name for e in found] == ["source", "gate", "drain"]

    def test_names_follow_position_left_to_right(self, contacts) -> None:
        found = {e.name: e for e in detect_electrodes(contacts)}
        assert found["source"].extent.x_max <= found["gate"].extent.x_min
        assert found["gate"].extent.x_max <= found["drain"].extent.x_min

    def test_gate_is_the_one_touching_poly(self, contacts) -> None:
        found = {e.name: e for e in detect_electrodes(contacts)}
        assert found["gate"].materials == ("poly",)

    def test_source_and_drain_touch_silicon(self, contacts) -> None:
        found = {e.name: e for e in detect_electrodes(contacts)}
        assert found["source"].materials == ("silicon",)
        assert found["drain"].materials == ("silicon",)

    def test_every_electrode_has_contact_edges(self, contacts) -> None:
        for electrode in detect_electrodes(contacts):
            assert electrode.edges, f"{electrode.name} 에 접촉 변이 없다"

    def test_contact_edges_belong_to_the_touched_region_not_the_metal(
        self, contacts
    ) -> None:
        """변은 **해석 대상 영역** 쪽 요소에 달려야 한다.

        DevSim 의 `add_gmsh_contact(region=...)` 이 접촉이 붙는 영역을 요구한다.
        금속 쪽 요소를 넘기면 그 영역은 해석에 없으므로 거부된다.
        """
        materials = {r.id: r.material for r in contacts.regions}
        for electrode in detect_electrodes(contacts):
            for edge in electrode.edges:
                assert materials[edge.region_id] != "aluminum"

    def test_semiconductor_mode_reports_semiconductor_contacts(
        self, contacts
    ) -> None:
        for electrode in detect_electrodes(contacts, gate_model=GateModel.SEMICONDUCTOR):
            assert electrode.kind is ContactKind.SEMICONDUCTOR

    def test_conductor_mode_puts_the_gate_on_the_oxide(self, contacts) -> None:
        """poly 를 도체로 보면 게이트 접촉은 산화막에 붙는다.

        DevSim 의 `CreateOxideContact` 가 받는 형태다. 소스·드레인은 그대로
        반도체 접촉이다.
        """
        found = {
            e.name: e for e in detect_electrodes(contacts, gate_model=GateModel.CONDUCTOR)
        }
        assert found["gate"].kind is ContactKind.INSULATOR
        assert found["gate"].materials == ("oxide",)
        assert found["source"].kind is ContactKind.SEMICONDUCTOR
        assert found["drain"].kind is ContactKind.SEMICONDUCTOR

    def test_no_metal_means_no_electrodes(self, cmos_2d) -> None:
        assert detect_electrodes(cmos_2d) == ()

    def test_extent_covers_the_contact_edges_only(self, contacts) -> None:
        """범위는 접촉 변에서 나와야 한다. 금속 덩어리 전체가 아니다.

        화면에 전극을 그릴 때 쓰는 값이라, 플러그 몸통까지 포함하면 실제로
        전류가 드나드는 자리를 가리키지 못한다.
        """
        found = {e.name: e for e in detect_electrodes(contacts)}
        gate = found["gate"]
        # 게이트 접촉은 poly 윗면이다. 플러그는 위로 한참 더 올라간다.
        assert gate.extent.y_max - gate.extent.y_min < 0.05
        # 절연막에 닿은 옆면은 전극에 들어오지 않는다.
        assert "oxide" not in gate.materials

    def test_edges_are_reported_as_point_pairs(self, contacts) -> None:
        limit = len(contacts.coordinates)
        for electrode in detect_electrodes(contacts):
            for edge in electrode.edges:
                assert len(edge.vertices) == 2
                assert edge.vertices[0] != edge.vertices[1]
                assert all(0 <= v < limit for v in edge.vertices)


class TestBacksideCandidate:
    def test_offers_the_backside_boundary(self, contacts) -> None:
        body = backside_candidate(contacts)
        assert body is not None
        assert body.name == "body"
        assert body.kind is ContactKind.SEMICONDUCTOR

    def test_sits_at_the_bottom_of_the_domain(self, contacts) -> None:
        body = backside_candidate(contacts)
        depth = max(c.y for c in contacts.coordinates)
        assert body.extent.y_min == pytest.approx(depth, abs=1e-6)

    def test_spans_the_full_width(self, contacts) -> None:
        body = backside_candidate(contacts)
        xs = [c.x for c in contacts.coordinates]
        assert body.extent.x_min == pytest.approx(min(xs), abs=1e-6)
        assert body.extent.x_max == pytest.approx(max(xs), abs=1e-6)

    def test_attaches_to_a_semiconductor_region(self, contacts) -> None:
        materials = {r.id: r.material for r in contacts.regions}
        body = backside_candidate(contacts)
        for edge in body.edges:
            assert materials[edge.region_id] == "silicon"


class TestConductorGateStaysOnThePolysilicon:
    """도체 모드에서 게이트 접촉이 층간 절연막까지 감싸면 안 된다.

    금속 플러그는 poly 와 한 덩어리지만, 플러그 옆면은 두꺼운 ILD 에 닿아 있다.
    그것까지 접촉으로 잡으면 게이트 전위가 ILD 전체에 걸리고, 실측에서 그
    구조는 초기해부터 수렴하지 않았다. 게이트로서 의미 있는 면은 poly 가
    맞닿은 면 — 게이트 산화막과 측벽 스페이서다.
    """

    def test_gate_contact_comes_from_the_polysilicon_side(self, contacts) -> None:
        materials = {r.id: r.material for r in contacts.regions}
        elements = list(contacts.elements)
        found = {
            e.name: e
            for e in detect_electrodes(contacts, gate_model=GateModel.CONDUCTOR)
        }
        gate = found["gate"]
        # 접촉 변마다, 반대편(도체 쪽) 요소가 poly 여야 한다.
        for edge in gate.edges:
            receiver = next(e for e in elements if e.id == edge.element_id)
            slot = [
                i
                for i, n in enumerate(receiver.neighbors)
                if n >= 0 and materials[elements[n].region_id] in {"aluminum", "poly"}
            ]
            assert slot, "도체와 맞닿지 않은 변이 게이트 접촉에 들어왔다"
            assert any(
                materials[elements[receiver.neighbors[i]].region_id] == "poly"
                for i in slot
            )

    def test_gate_contact_is_smaller_than_the_whole_cluster_boundary(
        self, contacts
    ) -> None:
        found = {
            e.name: e
            for e in detect_electrodes(contacts, gate_model=GateModel.CONDUCTOR)
        }
        semiconductor_mode = {
            e.name: e for e in detect_electrodes(contacts)
        }
        # 플러그 몸통까지 잡으면 세로 범위가 크게 늘어난다.
        gate = found["gate"]
        plug_top = semiconductor_mode["gate"].extent.y_min
        assert gate.extent.y_min >= plug_top - 0.4
