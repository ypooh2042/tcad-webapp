"""결과 시각화 엔드포인트.

`.str` 원문은 그대로 쓸 수 없다. 값이 좌표·물질·컬럼 순서에 흩어져 있고, 계면
점은 물질마다 값이 다르다. 화면에서 그걸 다시 풀게 하면 파서를 두 벌 유지하게
되므로 서버에서 그릴 수 있는 형태로 바꿔 보낸다.

소유 확인은 deps 의 owned_artifact 가 한다. 산출물에는 사용자가 쓴 코드의 결과가
들어 있으므로 남의 것을 읽히면 안 된다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import owned_artifact
from app.db.models import Artifact
from app.plotting.loader import load_structure
from app.plotting.profile import depth_profile, vertical_cut
from app.plotting.quantities import available
from app.plotting.surface import build_surface
from app.str_parser.errors import StructureFormatError
from app.str_parser.models import Structure

router = APIRouter(tags=["plot"])

#: 좌표는 마이크로미터 단위다. 6자리면 옹스트롬보다 촘촘해 화면에서 구분되지
#: 않는다. 그 아래는 페이로드만 키운다.
_COORDINATE_DIGITS = 6


class Bounds(BaseModel):
    x_min: float
    x_max: float
    y_min: float
    y_max: float


class StructureSummary(BaseModel):
    filename: str
    dimension: int
    quantities: list[str]
    materials: list[str]
    bounds: Bounds
    node_count: int
    element_count: int
    #: 파서가 남긴 경고. 조용히 삼키면 이상한 그림의 원인을 알 수 없다.
    warnings: list[str]


class ProfilePointResponse(BaseModel):
    depth: float
    value: float
    material: str


class ProfileResponse(BaseModel):
    quantity: str
    #: 2D 에서 어디를 잘랐는지. 1D 면 None.
    cut_x: float | None
    points: list[ProfilePointResponse]


class SurfaceResponse(BaseModel):
    quantity: str
    x: list[float]
    y: list[float]
    triangles: list[tuple[int, int, int]]
    values: list[tuple[float, float, float]]
    materials: list[str]
    value_min: float
    value_max: float


def _structure(artifact: Artifact) -> Structure:
    path = Path(artifact.path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="산출물이 정리되어 더 이상 남아 있지 않습니다",
        )
    try:
        return load_structure(path)
    except StructureFormatError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"구조 파일을 읽을 수 없습니다: {error}",
        ) from error


def _require_quantity(structure: Structure, quantity: str) -> None:
    if quantity not in available(structure):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"{quantity!r} 는 이 구조에 없습니다. "
                f"사용 가능: {list(available(structure))}"
            ),
        )


@router.get("/jobs/{job_id}/artifacts/{sequence}/structure")
async def summary(
    artifact: Artifact = Depends(owned_artifact),
) -> StructureSummary:
    """무엇을 그릴 수 있는지. 화면이 축과 물리량 목록을 정하는 근거다."""
    structure = _structure(artifact)
    xs = [coordinate.x for coordinate in structure.coordinates]
    ys = [coordinate.y for coordinate in structure.coordinates]

    return StructureSummary(
        filename=artifact.filename,
        dimension=structure.dimension,
        quantities=list(available(structure)),
        materials=sorted({region.material for region in structure.regions}),
        bounds=Bounds(
            x_min=min(xs, default=0.0),
            x_max=max(xs, default=0.0),
            y_min=min(ys, default=0.0),
            y_max=max(ys, default=0.0),
        ),
        node_count=len(structure.coordinates),
        element_count=len(structure.elements),
        warnings=list(structure.warnings),
    )


@router.get("/jobs/{job_id}/artifacts/{sequence}/profile")
async def profile(
    quantity: str = Query(min_length=1, max_length=64),
    x: float | None = Query(default=None),
    artifact: Artifact = Depends(owned_artifact),
) -> ProfileResponse:
    """깊이 프로파일.

    1D 는 x 를 받지 않는다(깊이가 곧 x 축이다). 2D 는 자를 가로 위치가 필요하다.
    """
    structure = _structure(artifact)
    _require_quantity(structure, quantity)

    if structure.dimension == 1:
        result = depth_profile(structure, quantity)
        cut_x = None
    else:
        if x is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="2D 구조는 자를 가로 위치 x 가 필요합니다",
            )
        result = vertical_cut(structure, x, quantity)
        cut_x = x

    return ProfileResponse(
        quantity=result.quantity,
        cut_x=cut_x,
        points=[
            ProfilePointResponse(
                depth=round(point.depth, _COORDINATE_DIGITS),
                value=point.value,
                material=point.material,
            )
            for point in result.points
        ],
    )


@router.get("/jobs/{job_id}/artifacts/{sequence}/surface")
async def surface(
    quantity: str = Query(min_length=1, max_length=64),
    artifact: Artifact = Depends(owned_artifact),
) -> SurfaceResponse:
    """2D 컨투어용 삼각형 목록."""
    structure = _structure(artifact)
    if structure.dimension != 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="1D 구조에는 단면이 없습니다. profile 을 쓰세요.",
        )
    _require_quantity(structure, quantity)

    built = build_surface(structure, quantity)
    low, high = built.value_range

    return SurfaceResponse(
        quantity=built.quantity,
        x=[round(value, _COORDINATE_DIGITS) for value in built.x],
        y=[round(value, _COORDINATE_DIGITS) for value in built.y],
        triangles=list(built.triangles),
        values=list(built.values),
        materials=list(built.materials),
        value_min=low,
        value_max=high,
    )
