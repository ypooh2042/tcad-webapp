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
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    current_session,
    get_app_settings,
    get_db,
    get_queue,
    owned_artifact,
    owned_job,
)
from app.api.throttle import throttle_submit
from app.auth.models import Session
from app.core.config import Settings
from app.db.models import Artifact, DevSimResult, Job, JobKind, JobStatus
from app.devsim.electrodes import Electrode, GateModel, detect_interfaces
from app.devsim.resolve import ElectrodeNotFound, resolve_electrodes
from app.devsim.screening import analysable
from app.devsim.service import place_structure
from app.devsim.spec import DeviceSpec, total_points
from app.jobs.queue import JobQueue
from app.plotting.loader import load_structure
from app.str_parser.errors import StructureFormatError
from app.str_parser.models import Structure

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
    job_id: int
    sequence: int
    spec: DeviceSpec


class SubmitResponse(BaseModel):
    id: int
    status: str
    total_points: int


class StructureArtifact(BaseModel):
    sequence: int
    filename: str


class StructureSource(BaseModel):
    """해석 입력으로 고를 수 있는 공정 실행 하나."""

    job_id: int
    source_path: str | None
    created_at: str
    artifacts: list[StructureArtifact]


class RunSummary(BaseModel):
    job_id: int
    label: str
    structure: str
    created_at: str
    completed: int
    total: int


class RunDetail(RunSummary):
    spec: dict
    data: dict


def _structure(artifact: Artifact) -> Structure:
    try:
        return load_structure(Path(artifact.path))
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="산출물이 정리되어 더 이상 남아 있지 않습니다",
        ) from None
    except StructureFormatError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


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


@router.get("/jobs/{job_id}/artifacts/{sequence}/interfaces")
async def interfaces(
    gate_model: GateModel = Query(default=GateModel.SEMICONDUCTOR),
    artifact: Artifact = Depends(owned_artifact),
) -> InterfacesResponse:
    """구조에서 자동으로 찾은 계면 — 금속 접촉과 뒷면 경계.

    규칙은 SUPREM 원본의 `IS_CONT`(`upstream/src/include/device.h:35`) 를 옮긴
    것이다. 같은 금속 덩어리에 닿은 변은 하나의 계면이 되고, 그래서 그 안의
    등전위는 **구성상** 보장된다. 여러 계면을 한 전위로 묶는 것은 전극이 한다.
    """
    structure = _structure(artifact)
    return InterfacesResponse(
        filename=artifact.filename,
        gate_model=gate_model.value,
        interfaces=[
            _describe(structure, found)
            for found in detect_interfaces(structure, gate_model=gate_model)
        ],
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
    artifact = await _owned(db, session, payload.job_id, payload.sequence)
    structure = _structure(artifact)

    # 전극이 실제로 잡히는지 **여기서** 확인한다. 워커까지 가서 실패하면
    # 사용자는 몇 분 뒤에야 오타를 알게 된다.
    spec = payload.spec.model_copy(update={"structure": artifact.filename})
    try:
        resolve_electrodes(structure, spec)
    except ElectrodeNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    # 경로는 서버가 정한다. 사용자 입력이 파일 경로에 섞이지 않는다.
    workdir = Path(settings.jobs_root).resolve() / f"job-{uuid4().hex}"
    try:
        place_structure(workdir, Path(artifact.path).read_text())
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="구조 파일을 읽지 못했습니다. 다시 실행한 뒤 시도해 주세요.",
        ) from error

    job = await queue.enqueue(
        owner_id=int(session.user_id),
        source_revision_id=None,
        workdir=str(workdir),
        source_path=artifact.filename,
        source=spec.model_dump_json(),
        kind=JobKind.DEVSIM,
    )
    return SubmitResponse(
        id=job.id, status=job.status.value, total_points=total_points(spec)
    )


async def _owned(
    db: AsyncSession, session: Session, job_id: int, sequence: int
) -> Artifact:
    job = await db.get(Job, job_id)
    if job is None or job.owner_id != int(session.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="잡을 찾을 수 없습니다"
        )
    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.job_id == job.id, Artifact.sequence == sequence
        )
    )
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="산출물을 찾을 수 없습니다"
        )
    return artifact


def _summary_of(row: DevSimResult, data: dict) -> RunSummary:
    return RunSummary(
        job_id=row.job_id,
        label=row.label,
        structure=row.structure,
        created_at=row.created_at.isoformat(),
        completed=int(data.get("completed", 0)),
        total=int(data.get("total", 0)),
    )


@router.get("/structures")
async def structures(
    limit: int = Query(default=20, ge=1, le=_MAX_RUNS),
    session: Session = Depends(current_session),
    db: AsyncSession = Depends(get_db),
) -> list[StructureSource]:
    """해석 입력으로 쓸 수 있는 구조들.

    `.str` 은 작업공간 파일 목록에 안 나온다(`app/workspace/service.py` — 실행
    결과라서 사용자가 직접 만들거나 지우는 것이 아니다). 그래서 잡 산출물에서
    뽑아 준다. 성공한 **공정 실행**만 고른다 — 해석 결과(`iv.json`)를 다시
    해석할 수는 없다.

    그리고 **전극이 있는 단계만** 올린다. 알루미늄이 실리콘이나 폴리실리콘에
    닿아야 전극이 된다(`app/devsim/screening.py`). 그렇지 않은 단계까지 올려
    두면 사용자는 고른 뒤에야 "전극이 없습니다"를 보고, 25단계짜리 흐름에서
    어느 단계부터 되는지 하나씩 눌러 보게 된다.
    """
    jobs = (
        await db.scalars(
            select(Job)
            .where(
                Job.owner_id == int(session.user_id),
                Job.kind == JobKind.SUPREM,
                Job.status == JobStatus.SUCCEEDED,
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(limit)
        )
    ).all()
    if not jobs:
        return []

    rows = await db.scalars(
        select(Artifact)
        .where(Artifact.job_id.in_([job.id for job in jobs]))
        .order_by(Artifact.job_id, Artifact.sequence)
    )
    grouped: dict[int, list[StructureArtifact]] = {}
    for artifact in rows:
        if not analysable(Path(artifact.path)):
            continue
        grouped.setdefault(artifact.job_id, []).append(
            StructureArtifact(
                sequence=artifact.sequence, filename=artifact.filename
            )
        )

    return [
        StructureSource(
            job_id=job.id,
            source_path=job.source_path,
            created_at=job.created_at.isoformat(),
            artifacts=grouped[job.id],
        )
        for job in jobs
        if job.id in grouped
    ]


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
