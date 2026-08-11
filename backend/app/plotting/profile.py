"""깊이 프로파일.

**축이 차원마다 다르다.** 실측으로 확인했다:

    1d_boron.str        x=[-0.075, 2.000]   y=[0, 0]
    2d_cmos_source.str  x=[0, 4.000]        y=[-0.406, 3.000]

1D 는 x 가 깊이이고 y 는 항상 0 이다. 2D 는 y 가 깊이이고 x 는 가로 위치다.
증착층은 깊이가 음수다(표면 위). 부호를 뒤집으면 산화막이 기판 아래에 그려진다.

계면 점은 물질마다 값이 다르므로 하나로 뭉개지 않고 물질을 함께 싣는다. 화면은
물질이 바뀌는 지점에서 선을 끊어 그리면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.plotting.quantities import value_of
from app.str_parser.models import Structure

#: 두 깊이를 같은 지점으로 볼 기준. 좌표는 마이크로미터 단위라 이보다 가까우면
#: 부동소수 오차다.
_DEPTH_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class ProfilePoint:
    depth: float
    value: float
    material: str


@dataclass(frozen=True, slots=True)
class Profile:
    quantity: str
    points: tuple[ProfilePoint, ...]

    @property
    def values(self) -> tuple[float, ...]:
        return tuple(point.value for point in self.points)


def depth_profile(structure: Structure, quantity: str) -> Profile:
    """1D 구조의 깊이 프로파일. x 가 깊이다."""
    if structure.dimension != 1:
        raise ValueError(
            f"1D 구조에서만 쓸 수 있습니다 (현재 {structure.dimension}D). "
            "2D 는 가로 위치를 지정해 vertical_cut 을 쓰세요."
        )

    # region 이 있는 물질만 싣는다. 1d_boron.str 에는 x=-0.075 에 ambient(기체)
    # 노드가 하나 있는데, region 목록에는 silicon 과 oxide 뿐이다. 즉 ambient 는
    # 시뮬레이션된 고체가 아니라 바깥쪽 경계다. 값도 1.0e8 짜리 자리표시자라,
    # 로그 축에서 이 점 하나가 축을 7제곱 아래로 끌어내려 정작 봐야 할
    # 프로파일을 못 읽게 만든다.
    #
    # 2D 의 vertical_cut 은 요소(=region 소속)를 훑으므로 자연히 같은 규칙이
    # 적용된다. 두 경로가 같은 물질 집합을 보게 맞춘다.
    solid_materials = {region.material_id for region in structure.regions}

    points = [
        ProfilePoint(
            depth=structure.coordinates[solution.coordinate_index].x,
            value=value_of(solution, quantity),
            material=solution.material,
        )
        for solution in structure.solutions
        if solution.material_id in solid_materials
    ]
    # 계면에서는 같은 깊이가 물질 수만큼 나온다. 물질 이름까지 정렬 키에 넣어야
    # 순서가 실행마다 흔들리지 않는다.
    points.sort(key=lambda point: (point.depth, point.material))
    return Profile(quantity=quantity, points=tuple(points))


def vertical_cut(structure: Structure, x: float, quantity: str) -> Profile:
    """2D 구조를 세로선 x 로 자른 깊이 프로파일.

    삼각형마다 세로선과 만나는 변을 찾아 선형 보간한다. 노드 값만 모으면 격자선
    위가 아닌 위치에서는 프로파일이 비어 버린다.
    """
    if structure.dimension != 2:
        raise ValueError(
            f"2D 구조에서만 쓸 수 있습니다 (현재 {structure.dimension}D)"
        )

    material_of_region = {region.id: region for region in structure.regions}
    collected: dict[tuple[int, str], ProfilePoint] = {}

    for element in structure.elements:
        region = material_of_region[element.region_id]
        try:
            values = [
                value_of(
                    structure.solution_at(vertex, region.material_id), quantity
                )
                for vertex in element.vertices
            ]
        except KeyError:
            # 이 요소의 물질 쪽 해가 없는 경우. 다른 물질 값으로 대체하면
            # 계면에서 값이 튀므로 건너뛴다.
            continue

        corners = [structure.coordinates[v] for v in element.vertices]

        for i in range(len(corners)):
            j = (i + 1) % len(corners)
            for point in _edge_crossings(
                corners[i], corners[j], values[i], values[j], x, region.material
            ):
                # 이웃한 삼각형이 같은 변을 공유하므로 같은 점이 여러 번 나온다.
                # 깊이를 반올림해 한 번만 남긴다.
                key = (round(point.depth / _DEPTH_EPSILON), point.material)
                collected.setdefault(key, point)

    points = sorted(collected.values(), key=lambda p: (p.depth, p.material))
    return Profile(quantity=quantity, points=tuple(points))


def _edge_crossings(
    start, end, start_value: float, end_value: float, x: float, material: str
):
    """변 하나가 세로선 x 와 만나는 지점.

    끝점이 선 위에 정확히 놓이는 경우를 따로 다룬다. 격자선 위를 자를 때가
    그런데, 이걸 빠뜨리면 프로파일에 구멍이 생긴다.
    """
    left = start.x - x
    right = end.x - x

    if left == 0.0:
        yield ProfilePoint(start.y, start_value, material)
    if right == 0.0:
        yield ProfilePoint(end.y, end_value, material)
    if left == 0.0 or right == 0.0:
        return

    if (left > 0.0) == (right > 0.0):
        return  # 같은 쪽에 있으니 만나지 않는다

    t = left / (left - right)
    yield ProfilePoint(
        depth=start.y + t * (end.y - start.y),
        value=start_value + t * (end_value - start_value),
        material=material,
    )
