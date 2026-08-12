"""프로젝트와 소스 리비전.

리비전은 만들어진 뒤 수정하지 않는다. 잡이 리비전을 참조하므로, 고치면 이미
끝난 잡의 입력이 뒤바뀌어 결과를 재현할 수 없다.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, Project, SourceRevision


class ProjectNotFound(Exception):
    """존재하지 않거나 요청자의 것이 아닌 프로젝트.

    "없음"과 "남의 것"을 구분하지 않는다. 구분해서 알리면 남의 프로젝트 id 를
    훑어 존재 여부를 알아낼 수 있다.
    """


class DuplicateProjectName(Exception):
    """같은 사용자가 같은 이름을 두 번 썼을 때."""


class ProjectBusy(Exception):
    """아직 끝나지 않은 잡이 있어 지울 수 없는 프로젝트.

    워커가 집어간 잡의 행이 실행 도중 사라지면 결과를 쓸 곳이 없어진다.
    """


async def create_project(
    session: AsyncSession, owner_id: int, name: str
) -> Project:
    existing = await session.scalar(
        select(Project).where(Project.owner_id == owner_id, Project.name == name)
    )
    if existing is not None:
        raise DuplicateProjectName(name)

    project = Project(owner_id=owner_id, name=name)
    session.add(project)
    await session.commit()
    return project


async def list_projects(
    session: AsyncSession, owner_id: int
) -> tuple[Project, ...]:
    result = await session.execute(
        select(Project)
        .where(Project.owner_id == owner_id)
        .order_by(Project.updated_at.desc())
    )
    return tuple(result.scalars().all())


async def get_owned_project(
    session: AsyncSession, project_id: int, owner_id: int
) -> Project:
    """소유자 확인까지 마친 프로젝트를 돌려준다.

    Raises:
        ProjectNotFound: 없거나 남의 것일 때.
    """
    project = await session.get(Project, project_id)
    if project is None or project.owner_id != owner_id:
        raise ProjectNotFound(project_id)
    return project


async def rename_project(
    session: AsyncSession, project_id: int, owner_id: int, name: str
) -> Project:
    """프로젝트 이름을 바꾼다. 소스와 잡은 건드리지 않는다.

    Raises:
        ProjectNotFound: 없거나 남의 것일 때.
        DuplicateProjectName: 같은 사용자가 이미 쓰고 있는 이름일 때.
    """
    project = await get_owned_project(session, project_id, owner_id)

    clash = await session.scalar(
        select(Project).where(
            Project.owner_id == owner_id,
            Project.name == name,
            # 자기 자신과 부딪힌다고 거절하면 사용자는 영문을 모른다.
            Project.id != project_id,
        )
    )
    if clash is not None:
        raise DuplicateProjectName(name)

    project.name = name
    await session.commit()
    return project


async def delete_project(
    session: AsyncSession, project_id: int, owner_id: int
) -> tuple[str, ...]:
    """프로젝트를 지운다. 리비전·잡·산출물이 외래키로 함께 사라진다.

    되돌릴 수 없다.

    Returns:
        딸려 사라진 잡들의 작업 디렉토리 경로. **디스크는 DB 가 지워 주지
        않으므로** 호출자가 이 경로들을 치워야 산출물이 남지 않는다.

    Raises:
        ProjectNotFound: 없거나 남의 것일 때.
        ProjectBusy: 아직 큐에 있거나 돌고 있는 잡이 있을 때.
    """
    project = await get_owned_project(session, project_id, owner_id)

    jobs = await session.scalars(
        select(Job)
        .join(SourceRevision, Job.source_revision_id == SourceRevision.id)
        .where(SourceRevision.project_id == project_id)
    )
    jobs = list(jobs)

    if any(not job.status.is_terminal for job in jobs):
        raise ProjectBusy(project_id)

    workdirs = tuple(job.workdir for job in jobs if job.workdir)
    await session.delete(project)
    await session.commit()
    # 잡과 산출물은 DB 가 ON DELETE CASCADE 로 지운다(passive_deletes). 세션은
    # 그 사실을 모르므로 식별 맵에 남은 옛 객체를 계속 돌려준다. 지워진 것만
    # 골라 떼어낸다 — expire_all 로 전부 만료시키면 다른 객체가 async 컨텍스트
    # 밖에서 lazy-load 를 시도해 터진다.
    for job in jobs:
        session.expunge(job)
    return workdirs


async def add_revision(
    session: AsyncSession, project: Project, source: str
) -> SourceRevision:
    """새 소스 리비전을 만든다. 번호는 프로젝트 안에서 1부터 증가한다."""
    latest = await session.scalar(
        select(func.max(SourceRevision.revision)).where(
            SourceRevision.project_id == project.id
        )
    )
    revision = SourceRevision(
        project_id=project.id,
        revision=(latest or 0) + 1,
        source=source,
    )
    session.add(revision)
    await session.commit()
    return revision


async def latest_revision(
    session: AsyncSession, project: Project
) -> SourceRevision | None:
    return await session.scalar(
        select(SourceRevision)
        .where(SourceRevision.project_id == project.id)
        .order_by(SourceRevision.revision.desc())
        .limit(1)
    )
