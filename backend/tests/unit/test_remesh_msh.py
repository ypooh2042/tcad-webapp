"""gmsh 출력(`.msh` 2.2) 읽기.

형식은 단순하지만 두 가지를 놓치기 쉽다.

    선 요소  — 경계 곡선에서 나온 2절점 요소가 섞여 있다. 삼각형만 가져가야 한다.
    물질     — 첫 태그가 Physical Surface 번호, 즉 우리가 넣은 영역 id 다.
               이걸 잃으면 어느 삼각형이 어느 물질인지 알 수 없다.
"""

from __future__ import annotations

import pytest

from app.remesh.msh import read_msh

SAMPLE = """$MeshFormat
2.2 0 8
$EndMeshFormat
$Nodes
4
1 0 0 0
2 1 0 0
3 1 1 0
4 0 1 0
$EndNodes
$Elements
3
1 1 2 7 1 1 2
2 2 2 5 1 1 2 3
3 2 2 6 1 1 3 4
$EndElements
"""


class TestReadMsh:
    def test_reads_nodes(self) -> None:
        mesh = read_msh(SAMPLE)

        assert mesh.points == ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))

    def test_keeps_only_triangles(self) -> None:
        # 경계 곡선에서 나온 선 요소를 삼각형으로 세면 메시가 망가진다.
        mesh = read_msh(SAMPLE)

        assert len(mesh.triangles) == 2

    def test_vertices_are_zero_based(self) -> None:
        """파일은 1-based 다. 내부는 파서와 같이 0-based 로 통일한다."""
        mesh = read_msh(SAMPLE)

        assert mesh.triangles[0].vertices == (0, 1, 2)

    def test_carries_the_region(self) -> None:
        mesh = read_msh(SAMPLE)

        assert [t.region_id for t in mesh.triangles] == [5, 6]

    def test_rejects_an_unknown_version(self) -> None:
        # 4.x 는 형식이 다르다. 조용히 잘못 읽느니 멈춘다.
        bad = SAMPLE.replace("2.2 0 8", "4.1 0 8")

        with pytest.raises(ValueError, match="2.2"):
            read_msh(bad)

    def test_rejects_a_file_without_triangles(self) -> None:
        empty = SAMPLE.replace("3\n1 1 2 7 1 1 2\n2 2 2 5 1 1 2 3\n3 2 2 6 1 1 3 4",
                               "1\n1 1 2 7 1 1 2")

        with pytest.raises(ValueError, match="삼각형"):
            read_msh(empty)
