"""소자 해석 엔드포인트.

세 가지를 한다.

1. **구조에서 계면을 찾아 보여준다.** 화면이 직접 `.str` 을 읽지 않는다 —
   그러면 파서를 두 벌 유지하게 된다. 플롯 쪽과 같은 이유다. 고를 수 있는
   것은 이 목록이 전부다. 임의의 경계를 전극으로 지정하게 두지 않는다.
2. **해석을 제출한다.** 제출 시점에 `.str` 을 잡 작업디렉토리로 복사한다.
   원본 잡의 산출물은 유휴·쿼터 스윕에 지워질 수 있는데, 그때 해석 입력이
   사라져 있으면 안 된다.
3. **끝난 해석을 돌려준다.** 비교 화면이 여러 건을 불러와 겹쳐 그린다.

소유 확인은 `deps.owned_artifact` / `owned_job` 이 한다. 남의 것은 403 이 아니라
404 다 — 403 으로 구분하면 id 를 훑어 존재 여부를 알아낼 수 있다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    current_session,
    get_app_settings,
    get_db,
    get_queue,
    owned_job,
)
from app.api.throttle import throttle_submit
from app.auth.models import Session
from app.core.config import Settings
from app.db.models import DevSimResult, DevSimState, Job, JobKind, SavedStructure
from app.devsim.electrodes import Electrode, GateModel, detect_interfaces
from app.devsim.resolve import ElectrodeNotFound, resolve_electrodes, restorable
from app.devsim.screening import analysable
from app.devsim.service import place_structure
from app.devsim.spec import DeviceSpec, total_points
from app.jobs.queue import JobQueue
from app.api.routes_plot import _COORDINATE_DIGITS, SurfaceResponse
from app.plotting.loader import load_structure
from app.plotting.surface import build_surface
from app.str_parser.errors import StructureFormatError
from app.str_parser.models import Structure

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devsim", tags=["devsim"])

#: 비교 목록 한 번에 돌려줄 최대 건수.
_MAX_RUNS = 50


class ExtentResponse(BaseModel):
    x_min: float
    x_max: float
    y_min: float
    y_max: float


class InterfaceResponse(BaseModel):
    """자동으로 찾은 계면 하나. 전극에 붙일 수 있는 최소 단위다."""

    #: 스펙이 이 계면을 가리킬 때 쓰는 열쇠. 같은 구조·같은 게이트 모델이면
    #: 항상 같게 나온다.
    key: str
    #: `metal` 금속-반도체(또는 금속-절연막) 접촉, `backside` 뒷면 경계.
    origin: str
    kind: str
    materials: list[str]
    extent: ExtentResponse
    edge_count: int
    #: 화면에 그릴 선분들. 좌표는 µm 이며 플롯과 같은 좌표계다.
    segments: list[list[float]]


class InterfacesResponse(BaseModel):
    filename: str
    gate_model: str
    interfaces: list[InterfaceResponse]


class SubmitRequest(BaseModel):
    structure_id: int
    spec: DeviceSpec


class SubmitResponse(BaseModel):
    id: int
    status: str
    total_points: int


class SavedStructureResponse(BaseModel):
    """보관해 둔 구조 하나."""

    id: int
    filename: str
    #: 공정 단계 순서. 결과 화면에서 넘어올 때 짝을 찾는 데 쓴다.
    sequence: int
    #: 만들어 낸 잡. 잡이 지워졌으면 비어 있다.
    job_id: int | None
    size_bytes: int


class StructureSource(BaseModel):
    """`.in` 하나에서 나온 구조들."""

    source_path: str
    created_at: str
    structures: list[SavedStructureResponse]


class RunSummary(BaseModel):
    job_id: int
    label: str
    structure: str
    #: 이 결과를 만든 `.in`. 비교 화면이 출처를 보여줄 때 쓴다.
    source_path: str
    created_at: str
    completed: int
    total: int


class SaveRequest(BaseModel):
    job_id: int
    label: str = Field(min_length=1, max_length=120)


class RenameRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)


class RunDetail(RunSummary):
    spec: dict
    data: dict


def _structure(saved: SavedStructure) -> Structure:
    try:
        return load_structure(Path(saved.path))
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="산출물이 정리되어 더 이상 남아 있지 않습니다",
        ) from None
    except StructureFormatError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


async def _owned_structure(
    structure_id: int,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> SavedStructure:
    """소유 확인을 마친 보관 구조. 남의 것은 403 이 아니라 404 다."""
    found = await db.get(SavedStructure, structure_id)
    if found is None or found.owner_id != int(session.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="구조를 찾을 수 없습니다"
        )
    return found


def _segments(structure: Structure, electrode: Electrode) -> list[list[float]]:
    """`[x0, y0, x1, y1]` 목록. 화면이 그대로 선으로 그린다."""
    lines: list[list[float]] = []
    for edge in electrode.edges:
        a = structure.coordinates[edge.vertices[0]]
        b = structure.coordinates[edge.vertices[1]]
        lines.append([round(a.x, 6), round(a.y, 6), round(b.x, 6), round(b.y, 6)])
    return lines


def _describe(structure: Structure, electrode: Electrode) -> InterfaceResponse:
    return InterfaceResponse(
        key=electrode.name,
        origin=electrode.origin,
        kind=electrode.kind.value,
        materials=list(electrode.materials),
        extent=ExtentResponse(
            x_min=electrode.extent.x_min,
            x_max=electrode.extent.x_max,
            y_min=electrode.extent.y_min,
            y_max=electrode.extent.y_max,
        ),
        edge_count=len(electrode.edges),
        segments=_segments(structure, electrode),
    )


@router.get("/structures/{structure_id}/interfaces")
async def interfaces(
    gate_model: GateModel = Query(default=GateModel.SEMICONDUCTOR),
    saved: SavedStructure = Depends(_owned_structure),
) -> InterfacesResponse:
    """구조에서 자동으로 찾은 계면 — 금속 접촉과 뒷면 경계.

    규칙은 SUPREM 원본의 `IS_CONT`(`upstream/src/include/device.h:35`) 를 옮긴
    것이다. 같은 금속 덩어리에 닿은 변은 하나의 계면이 되고, 그래서 그 안의
    등전위는 **구성상** 보장된다. 여러 계면을 한 전위로 묶는 것은 전극이 한다.
    """
    structure = _structure(saved)
    return InterfacesResponse(
        filename=saved.filename,
        gate_model=gate_model.value,
        interfaces=[
            _describe(structure, found)
            for found in detect_interfaces(structure, gate_model=gate_model)
        ],
    )


class StateBody(BaseModel):
    spec: DeviceSpec


class StateResponse(BaseModel):
    spec: DeviceSpec


@router.get("/structures/{structure_id}/state")
async def read_state(
    saved: SavedStructure = Depends(_owned_structure),
    db: AsyncSession = Depends(get_db),
) -> StateResponse:
    """맡아 둔 해석 조건. 없거나 지금 구조에 안 맞으면 404.

    404 는 "기본값으로 시작하라" 는 뜻이다. 맞지 않는 조건을 억지로 되살리면
    사용자는 자기가 짠 적 없는 설정을 자기 것으로 알고 읽게 된다.
    """
    row = await db.get(DevSimState, (saved.owner_id, saved.source_path))
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="맡아 둔 조건이 없습니다"
        )
    try:
        spec = DeviceSpec.model_validate_json(row.spec)
        restorable(_structure(saved), spec)
    except (ValueError, ElectrodeNotFound):
        logger.info(
            "맡아 둔 조건이 지금 구조에 맞지 않아 버립니다: %s", saved.source_path
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="맡아 둔 조건이 지금 구조에 맞지 않습니다",
        ) from None
    return StateResponse(spec=spec)


@router.put("/structures/{structure_id}/state", status_code=status.HTTP_204_NO_CONTENT)
async def write_state(
    payload: StateBody,
    saved: SavedStructure = Depends(_owned_structure),
    db: AsyncSession = Depends(get_db),
) -> None:
    """해석 조건을 맡아 둔다. 지금 구조에 안 맞으면 거절한다.

    못 쓸 조건을 맡아 두면, 다음에 열었을 때 조용히 버려지는 것으로 끝난다 —
    저장이 된 줄 알았던 사용자에게는 그것이 곧 데이터를 잃은 일이다.
    """
    try:
        restorable(_structure(saved), payload.spec)
    except ElectrodeNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    row = await db.get(DevSimState, (saved.owner_id, saved.source_path))
    if row is None:
        row = DevSimState(owner_id=saved.owner_id, source_path=saved.source_path)
        db.add(row)
    row.spec = payload.spec.model_dump_json()
    await db.commit()


@router.get("/structures/{structure_id}/surface")
async def surface(
    saved: SavedStructure = Depends(_owned_structure),
) -> SurfaceResponse:
    """단면 그림. 재질만 칠한다.

    플롯 쪽에도 같은 것이 있지만 그쪽은 **잡 산출물**을 본다. 산출물은 스윕에
    지워지므로, 공정을 돌린 다음 날에도 전극을 짚으려면 보관본에서 그려야 한다.
    """
    built = build_surface(_structure(saved), None)
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


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def submit(
    payload: SubmitRequest,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
    queue: JobQueue = Depends(get_queue),
    settings: Settings = Depends(get_app_settings),
    _: None = Depends(throttle_submit),
) -> SubmitResponse:
    """해석을 큐에 넣는다."""
    saved = await db.get(SavedStructure, payload.structure_id)
    if saved is None or saved.owner_id != int(session.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="구조를 찾을 수 없습니다"
        )
    structure = _structure(saved)

    # 전극이 실제로 잡히는지 **여기서** 확인한다. 워커까지 가서 실패하면
    # 사용자는 몇 분 뒤에야 오타를 알게 된다.
    spec = payload.spec.model_copy(update={"structure": saved.filename})
    try:
        resolve_electrodes(structure, spec)
    except ElectrodeNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    # 경로는 서버가 정한다. 사용자 입력이 파일 경로에 섞이지 않는다.
    workdir = Path(settings.jobs_root).resolve() / f"job-{uuid4().hex}"
    try:
        place_structure(workdir, Path(saved.path).read_text())
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="구조 파일을 읽지 못했습니다. 다시 실행한 뒤 시도해 주세요.",
        ) from error

    job = await queue.enqueue(
        owner_id=int(session.user_id),
        source_revision_id=None,
        workdir=str(workdir),
        source_path=saved.source_path,
        source=spec.model_dump_json(),
        kind=JobKind.DEVSIM,
    )
    return SubmitResponse(
        id=job.id, status=job.status.value, total_points=total_points(spec)
    )


def _summary_of(row: DevSimResult, data: dict) -> RunSummary:
    return RunSummary(
        job_id=row.job_id,
        label=row.label,
        structure=row.structure,
        source_path=row.source_path,
        created_at=row.created_at.isoformat(),
        completed=int(data.get("completed", 0)),
        total=int(data.get("total", 0)),
    )


def _dataset_of(job: Job) -> dict:
    """잡이 남긴 곡선. 산출물에서 읽는다.

    표에는 사용자가 이름을 붙여 저장한 것만 들어간다. 방금 돌린 결과를 보려면
    산출물을 봐야 한다.
    """
    if job.kind != JobKind.DEVSIM:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="소자 해석 잡이 아닙니다"
        )
    path = Path(job.workdir) / "iv.json"
    try:
        return _loads(path.read_text())
    except OSError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="결과가 정리되어 더 이상 남아 있지 않습니다",
        ) from None


@router.get("/jobs/{job_id}/result")
async def job_result(job: Job = Depends(owned_job)) -> dict:
    """방금 돌린 해석의 곡선."""
    return _dataset_of(job)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def save_run(
    payload: SaveRequest,
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> RunSummary:
    """해석 결과에 이름을 붙여 남긴다."""
    job = await db.get(Job, payload.job_id)
    if job is None or job.owner_id != int(session.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="잡을 찾을 수 없습니다"
        )
    data = _dataset_of(job)
    if not data.get("rows"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="풀린 점이 없어 저장할 것이 없습니다",
        )

    spec = _loads(job.source or "{}")
    row = await db.get(DevSimResult, job.id)
    if row is None:
        row = DevSimResult(job_id=job.id, owner_id=job.owner_id)
        db.add(row)
    # 같은 잡을 다시 저장하면 이름만 바뀐다. 같은 곡선이 두 줄로 쌓이면
    # 비교 목록에서 어느 쪽이 무엇인지 구분할 수 없다.
    row.label = payload.label
    row.structure = str(spec.get("structure") or "")[:255]
    row.source_path = str(job.source_path or "")[:1024]
    row.spec = job.source or "{}"
    row.data = json.dumps(data)
    await db.commit()
    return _summary_of(row, data)


@router.patch("/runs/{job_id}")
async def rename_run(
    payload: RenameRequest,
    job: Job = Depends(owned_job),
    db: AsyncSession = Depends(get_db),
) -> RunSummary:
    row = await db.get(DevSimResult, job.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="저장된 해석 결과가 없습니다",
        )
    row.label = payload.label
    await db.commit()
    return _summary_of(row, _loads(row.data))


@router.delete("/runs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_run(
    job: Job = Depends(owned_job),
    db: AsyncSession = Depends(get_db),
) -> None:
    row = await db.get(DevSimResult, job.id)
    if row is not None:
        await db.delete(row)
        await db.commit()


@router.get("/structures")
async def structures(
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> list[StructureSource]:
    """해석 입력으로 쓸 수 있는 구조들.

    **보관소에서 읽는다.** 잡 산출물은 유휴·쿼터 스윕에 지워지므로 그대로 쓰면
    공정을 돌린 다음 날 해석할 수 없다. 워커가 공정을 끝낼 때 전극이 있는 것만
    골라 여기에 옮겨 둔다(`app/devsim/catalog.py`).

    같은 `.in` 을 다시 돌리면 그 `.in` 의 옛 구조는 사라지고 새것으로 바뀐다.
    """
    rows = (
        await db.scalars(
            select(SavedStructure)
            .where(SavedStructure.owner_id == int(session.user_id))
            .order_by(
                SavedStructure.source_path,
                SavedStructure.sequence,
                SavedStructure.id,
            )
        )
    ).all()

    grouped: dict[str, StructureSource] = {}
    for row in rows:
        source = grouped.get(row.source_path)
        if source is None:
            source = StructureSource(
                source_path=row.source_path,
                created_at=row.created_at.isoformat(),
                structures=[],
            )
            grouped[row.source_path] = source
        source.structures.append(
            SavedStructureResponse(
                id=row.id,
                filename=row.filename,
                sequence=row.sequence,
                job_id=row.job_id,
                size_bytes=row.size_bytes,
            )
        )
    return sorted(grouped.values(), key=lambda one: one.created_at, reverse=True)


@router.get("/runs")
async def runs(
    limit: int = Query(default=20, ge=1, le=_MAX_RUNS),
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> list[RunSummary]:
    """끝난 해석 목록. 비교 화면이 여기서 고른다."""
    rows = await db.scalars(
        select(DevSimResult)
        .where(DevSimResult.owner_id == int(session.user_id))
        .order_by(DevSimResult.created_at.desc(), DevSimResult.job_id.desc())
        .limit(limit)
    )
    result: list[RunSummary] = []
    for row in rows:
        result.append(_summary_of(row, _loads(row.data)))
    return result


@router.get("/runs/{job_id}")
async def run_detail(
    job: Job = Depends(owned_job),
    db: AsyncSession = Depends(get_db),
) -> RunDetail:
    """해석 하나의 곡선 전체."""
    row = await db.get(DevSimResult, job.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="이 잡에는 저장된 해석 결과가 없습니다",
        )
    data = _loads(row.data)
    summary = _summary_of(row, data)
    return RunDetail(
        **summary.model_dump(), spec=_loads(row.spec), data=data
    )


def _loads(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
