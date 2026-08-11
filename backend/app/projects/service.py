"""프로젝트와 소스 리비전.

리비전은 만들어진 뒤 수정하지 않는다. 잡이 리비전을 참조하므로, 고치면 이미
끝난 잡의 입력이 뒤바뀌어 결과를 재현할 수 없다.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project, SourceRevision


class ProjectNotFound(Exception):
    """존재하지 않거나 요청자의 것이 아닌 프로젝트.

    "없음"과 "남의 것"을 구분하지 않는다. 구분해서 알리면 남의 프로젝트 id 를
    훑어 존재 여부를 알아낼 수 있다.
    """


class DuplicateProjectName(Exception):
    """같은 사용자가 같은 이름을 두 번 썼을 때."""


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
