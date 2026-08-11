"""SUPREM4GS `.str` 구조 파일 파싱.

공개 API 는 `parse_structure` 하나다.
"""

from app.str_parser.errors import StructureFormatError
from app.str_parser.models import (
    Coordinate,
    Element,
    NodeSolution,
    Region,
    Structure,
)
from app.str_parser.parser import parse_structure

__all__ = [
    "Coordinate",
    "Element",
    "NodeSolution",
    "Region",
    "Structure",
    "StructureFormatError",
    "parse_structure",
]
