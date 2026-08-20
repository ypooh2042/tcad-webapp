"""`.str` → DevSim 장치 메쉬 변환 테스트.

형식은 실측으로 확인한 것이다. `devsim.create_gmsh_mesh` 는 파일 없이
배열만으로도 메쉬를 받는다:

    coordinates    = [x0,y0,z0, x1,y1,z1, ...]
    elements       = [타입, physical 인덱스(0-based), 노드...]  가 이어붙은 평평한 리스트
                     타입 1 = 변(노드 2개), 2 = 삼각형(노드 3개)
    physical_names = 영역·계면·접촉 이름

단위는 cm 계다(`simple_physics.py` 가 `eps_0 = 8.85e-14 F/cm` 를 쓴다).
SUPREM 은 µm 에 y 가 깊이 방향(아래가 +)이므로 ×1e-4 와 y 부호 뒤집기가 필요하다.
"""

from pathlib import Path

import pytest

from app.devsim.electrodes import GateModel, backside_candidate, detect_electrodes
from app.devsim.mesh import (
    EDGE,
    TRIANGLE,
    UM_TO_CM,
    build_device_mesh,
    iter_elements,
)
from app.str_parser import parse_structure
from app.str_parser.mesh import signed_area

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def contacts():
    return parse_structure((FIXTURES / "2d_contacts.str").read_text())


@pytest.fixture
def device(contacts):
    electrodes = (*detect_electrodes(contacts), backside_candidate(contacts))
    return build_device_mesh(contacts, electrodes)


class TestRegionSelection:
    def test_metal_never_becomes_a_region(self, device) -> None:
        assert all(r.material != "aluminum" for r in device.regions)

    def test_semiconductors_are_kept(self, device) -> None:
        materials = {r.material for r in device.regions}
        assert "silicon" in materials
        assert "poly" in materials

    def test_conductor_mode_drops_poly_as_a_region(self, contacts) -> None:
        electrodes = detect_electrodes(contacts, gate_model=GateModel.CONDUCTOR)
        built = build_device_mesh(
            contacts, electrodes, gate_model=GateModel.CONDUCTOR
        )
        assert all(r.material != "poly" for r in built.regions)

    def test_every_region_name_is_unique(self, device) -> None:
        names = [r.name for r in device.regions]
        assert len(names) == len(set(names))


class TestCoordinates:
    def test_three_floats_per_point(self, device) -> None:
        assert len(device.coordinates) % 3 == 0
        assert len(device.coordinates) // 3 == len(device.point_map)

    def test_z_is_always_zero(self, device) -> None:
        assert set(device.coordinates[2::3]) == {0.0}

    def test_converted_to_centimetres(self, contacts, device) -> None:
        """DevSim 은 cm 계다. µm 그대로 넘기면 소자가 1만 배 커진다."""
        source_index, target_index = next(iter(device.point_map.items()))
        point = contacts.coordinates[source_index]
        assert device.coordinates[target_index * 3] == pytest.approx(
            point.x * UM_TO_CM
        )

    def test_depth_axis_is_flipped(self, contacts, device) -> None:
        """SUPREM 은 아래가 +y 다. 뒤집지 않으면 삼각형 방향이 전부 반대가 된다."""
        source_index, target_index = next(iter(device.point_map.items()))
        point = contacts.coordinates[source_index]
        assert device.coordinates[target_index * 3 + 1] == pytest.approx(
            -point.y * UM_TO_CM
        )

    def test_only_used_points_are_shipped(self, contacts, device) -> None:
        # 금속을 빼면 그 안쪽에만 있던 점은 쓸 데가 없다.
        assert len(device.point_map) < len(contacts.coordinates)


class TestElements:
    def test_every_record_is_readable(self, device) -> None:
        for kind, physical, nodes in iter_elements(device.elements):
            assert kind in (EDGE, TRIANGLE)
            assert len(nodes) == (2 if kind == EDGE else 3)
            assert 0 <= physical < len(device.physical_names)

    def test_node_indices_stay_in_range(self, device) -> None:
        limit = len(device.coordinates) // 3
        for _kind, _physical, nodes in iter_elements(device.elements):
            assert all(0 <= n < limit for n in nodes)

    def test_triangle_count_matches_the_selected_regions(
        self, contacts, device
    ) -> None:
        kept = {r.region_id for r in device.regions}
        expected = sum(1 for e in contacts.elements if e.region_id in kept)
        actual = sum(
            1 for kind, _p, _n in iter_elements(device.elements) if kind == TRIANGLE
        )
        assert actual == expected

    def test_triangles_are_counter_clockwise(self, device) -> None:
        """y 를 뒤집으면 방향이 반대가 된다. 넘기기 전에 바로잡아야 한다."""
        coordinates = device.coordinates
        for kind, _physical, nodes in iter_elements(device.elements):
            if kind != TRIANGLE:
                continue
            (ax, ay), (bx, by), (cx, cy) = (
                (coordinates[n * 3], coordinates[n * 3 + 1]) for n in nodes
            )
            area = 0.5 * ((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))
            assert area > 0

    def test_area_is_preserved(self, contacts, device) -> None:
        kept = {r.region_id for r in device.regions}
        original = sum(
            abs(signed_area(contacts, e))
            for e in contacts.elements
            if e.region_id in kept
        )
        coordinates = device.coordinates
        moved = 0.0
        for kind, _physical, nodes in iter_elements(device.elements):
            if kind != TRIANGLE:
                continue
            (ax, ay), (bx, by), (cx, cy) = (
                (coordinates[n * 3], coordinates[n * 3 + 1]) for n in nodes
            )
            moved += abs(0.5 * ((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)))
        assert moved == pytest.approx(original * UM_TO_CM**2, rel=1e-9)


class TestInterfaces:
    def test_interfaces_join_two_selected_regions(self, device) -> None:
        names = {r.name for r in device.regions}
        for interface in device.interfaces:
            assert interface.region0 in names
            assert interface.region1 in names
            assert interface.region0 != interface.region1

    def test_silicon_meets_the_gate_oxide(self, device) -> None:
        pairs = {
            frozenset((i.region0, i.region1)): i.name for i in device.interfaces
        }
        by_name = {r.name: r.material for r in device.regions}
        joined = {
            frozenset(sorted((by_name[a], by_name[b])))
            for pair in pairs
            for a, b in [tuple(pair)]
        }
        assert frozenset({"silicon", "oxide"}) in joined

    def test_each_interface_edge_appears_once(self, device) -> None:
        seen: set[tuple[int, int]] = set()
        interface_ids = {
            device.physical_names.index(i.name) for i in device.interfaces
        }
        for kind, physical, nodes in iter_elements(device.elements):
            if kind != EDGE or physical not in interface_ids:
                continue
            key = (min(nodes), max(nodes))
            assert key not in seen, "계면 변이 두 번 들어갔다"
            seen.add(key)


class TestContacts:
    def test_every_electrode_produces_a_contact(self, device) -> None:
        electrodes = {c.electrode for c in device.contacts}
        assert electrodes == {"source", "gate", "drain", "body"}

    def test_contact_names_are_unique(self, device) -> None:
        names = [c.name for c in device.contacts]
        assert len(names) == len(set(names))

    def test_contact_attaches_to_a_selected_region(self, device) -> None:
        names = {r.name for r in device.regions}
        assert all(c.region in names for c in device.contacts)

    def test_contact_edges_are_emitted(self, device) -> None:
        contact_ids = {device.physical_names.index(c.name) for c in device.contacts}
        counted = sum(
            1
            for kind, physical, _n in iter_elements(device.elements)
            if kind == EDGE and physical in contact_ids
        )
        assert counted > 0

    def test_physical_names_cover_everything(self, device) -> None:
        expected = (
            {r.name for r in device.regions}
            | {i.name for i in device.interfaces}
            | {c.name for c in device.contacts}
        )
        assert set(device.physical_names) == expected
