"""`.str` 구조 파일 파서.

라인 접두 문자로 종류가 갈리는 텍스트 포맷이다. 포맷 근거는
SUPREM4GS/STR_FILE_FORMAT.md 참조 (실제 실행 결과와 postmini 추출값을 대조해 검증).
"""

from __future__ import annotations

from types import MappingProxyType

from app.str_parser.errors import StructureFormatError
from app.str_parser.materials import is_known_material, resolve_material
from app.str_parser.models import (
    Coordinate,
    Element,
    NodeSolution,
    Region,
    Structure,
)
from app.str_parser.species import SpeciesTable, build_species_table

_COORD_FIELDS_1D = 3  # id x <리터럴 0>
_TRAILING_FIELDS = 2  # 의미 미확정, 원본 보존
_COORD_FIELDS_2D = 4  # id x y <리터럴 0>


class _Accumulator:
    """파싱 중간 상태. 완성되면 불변 Structure 로 굳힌다."""

    def __init__(self) -> None:
        self.version = ""
        self.dimension = 1
        self.vertices_per_element = 2
        self.neighbors_per_element = 2
        self.coordinates: list[Coordinate] = []
        self.regions: list[Region] = []
        self.elements: list[Element] = []
        self.temperature_k: float | None = None
        self.table: SpeciesTable | None = None
        self.solution_rows: list[tuple[int, int, tuple[float, ...]]] = []
        self.warnings: list[str] = []


def parse_structure(text: str) -> Structure:
    """`.str` 파일 내용을 파싱한다.

    Raises:
        StructureFormatError: 포맷 불변식을 위반한 경우. 잘못된 값을 조용히
            반환하는 것보다 즉시 실패하는 편이 안전하다.
    """
    acc = _Accumulator()

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            _consume_line(acc, line)
        except StructureFormatError:
            raise
        except (ValueError, IndexError) as exc:
            raise StructureFormatError(
                f"{line_number}행을 해석할 수 없습니다: {raw_line!r}"
            ) from exc

    return _finalize(acc)


def _consume_line(acc: _Accumulator, line: str) -> None:
    tag, _, rest = line.partition(" ")
    handler = _HANDLERS.get(tag)
    if handler is None:
        acc.warnings.append(f"알 수 없는 라인 종류 {tag!r} 를 건너뜁니다")
        return
    handler(acc, rest.split())


def _handle_version(acc: _Accumulator, fields: list[str]) -> None:
    acc.version = " ".join(fields)


def _handle_dimension(acc: _Accumulator, fields: list[str]) -> None:
    """`D <mode> <nvrt> <nedg>`.

    ig2_write 가 mode/nvrt/nedg 전역을 그대로 출력한다. 이 세 값이 `t` 라인의
    필드 배치를 결정하므로 추측하지 않고 여기서 읽어 쓴다.
    """
    acc.dimension = int(fields[0])
    acc.vertices_per_element = int(fields[1])
    acc.neighbors_per_element = int(fields[2])


def _handle_coordinate(acc: _Accumulator, fields: list[str]) -> None:
    """1D 는 `c <id> <x> <flag>`, 2D 는 `c <id> <x> <y> <flag>`.

    필드 수로 구분한다. D 라인이 앞에 나오긴 하지만 필드 수가 더 직접적인 근거다.
    """
    if len(fields) == _COORD_FIELDS_2D:
        acc.coordinates.append(
            Coordinate(id=int(fields[0]), x=float(fields[1]), y=float(fields[2]))
        )
    elif len(fields) == _COORD_FIELDS_1D:
        acc.coordinates.append(
            Coordinate(id=int(fields[0]), x=float(fields[1]), y=0.0)
        )
    else:
        raise StructureFormatError(
            f"좌표 라인의 필드 수가 예상 밖입니다: {len(fields)}개 ({fields})"
        )


def _handle_region(acc: _Accumulator, fields: list[str]) -> None:
    material_id = int(fields[1])
    if not is_known_material(material_id):
        acc.warnings.append(
            f"미확인 material_id {material_id} — unknown 으로 보존합니다"
        )
    acc.regions.append(
        Region(
            id=int(fields[0]),
            material_id=material_id,
            material=resolve_material(material_id),
        )
    )


def _handle_element(acc: _Accumulator, fields: list[str]) -> None:
    """`t <id> <region_id> <정점 nvrt개> <이웃 nedg개> <미확정 2개>`."""
    nvrt = acc.vertices_per_element
    nedg = acc.neighbors_per_element
    expected = 2 + nvrt + nedg + _TRAILING_FIELDS
    if len(fields) != expected:
        raise StructureFormatError(
            f"요소 라인 필드가 {expected}개여야 하는데 {len(fields)}개입니다 "
            f"(D 라인 기준 nvrt={nvrt}, nedg={nedg})"
        )

    values = [int(f) for f in fields]
    vertex_end = 2 + nvrt
    neighbor_end = vertex_end + nedg

    acc.elements.append(
        Element(
            id=values[0],
            region_id=values[1],
            # 파일은 1-based 좌표 인덱스, 내부는 0-based 로 통일한다.
            vertices=tuple(v - 1 for v in values[2:vertex_end]),
            # 1 이상이면 요소 참조라 0-based 로 낮추고, 0 이하는 경계 조건
            # 코드이므로 손대지 않는다.
            neighbors=tuple(
                n - 1 if n > 0 else n for n in values[vertex_end:neighbor_end]
            ),
            extra=tuple(values[neighbor_end:]),
        )
    )


def _handle_temperature(acc: _Accumulator, fields: list[str]) -> None:
    acc.temperature_k = float(fields[1])


def _handle_species(acc: _Accumulator, fields: list[str]) -> None:
    declared = int(fields[0])
    codes = [int(f) for f in fields[1:]]
    if declared != len(codes):
        raise StructureFormatError(
            f"s 라인이 species {declared}개를 선언했지만 코드는 {len(codes)}개입니다"
        )
    acc.table = build_species_table(codes)
    for species in acc.table.species:
        if not species.is_known:
            acc.warnings.append(
                f"미확인 species 코드 {species.code} — {species.name} 으로 보존합니다"
            )


def _handle_node(acc: _Accumulator, fields: list[str]) -> None:
    if acc.table is None:
        raise StructureFormatError("s 라인보다 n 라인이 먼저 나왔습니다")

    values = tuple(float(f) for f in fields[2:])
    if len(values) != len(acc.table):
        raise StructureFormatError(
            f"species 개수는 {len(acc.table)}인데 노드 값은 {len(values)}개입니다"
        )

    material_id = int(fields[1])
    if not is_known_material(material_id):
        acc.warnings.append(
            f"미확인 material_id {material_id} — unknown 으로 보존합니다"
        )

    # 첫 필드는 이미 0-based 좌표 인덱스다(mk_nd 의 pt 인자). 변환하지 않는다.
    acc.solution_rows.append((int(fields[0]), material_id, values))


def _handle_interface(acc: _Accumulator, fields: list[str]) -> None:
    """`I` 라인. 인터페이스 레코드. 현재 쓰는 곳이 없어 보존만 한다."""


_HANDLERS = {
    "v": _handle_version,
    "D": _handle_dimension,
    "c": _handle_coordinate,
    "r": _handle_region,
    "t": _handle_element,
    "M": _handle_temperature,
    "s": _handle_species,
    "n": _handle_node,
    "I": _handle_interface,
}


def _finalize(acc: _Accumulator) -> Structure:
    if acc.table is None:
        raise StructureFormatError("s 라인이 없어 컬럼 배치를 알 수 없습니다")

    solutions = tuple(
        NodeSolution(
            coordinate_index=coordinate_index,
            material_id=material_id,
            material=resolve_material(material_id),
            values=values,
            table=acc.table,
        )
        for coordinate_index, material_id, values in acc.solution_rows
    )

    return Structure(
        version=acc.version,
        dimension=acc.dimension,
        vertices_per_element=acc.vertices_per_element,
        neighbors_per_element=acc.neighbors_per_element,
        coordinates=tuple(acc.coordinates),
        regions=tuple(acc.regions),
        elements=tuple(acc.elements),
        solutions=solutions,
        table=acc.table,
        temperature_k=acc.temperature_k,
        warnings=tuple(acc.warnings),
        _solution_index=MappingProxyType(
            {(s.coordinate_index, s.material_id): s for s in solutions}
        ),
    )
