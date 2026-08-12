"""프로젝트 이름 바꾸기와 삭제.

삭제는 되돌릴 수 없다. 리비전과 잡과 산출물이 외래키로 딸려 있어 프로젝트를
지우면 전부 함께 사라진다 — 그래서 **돌고 있는 잡이 있으면 거절한다.** 워커가
집어간 잡의 행이 실행 도중 사라지면 결과를 쓸 곳이 없어진다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base, Job, JobStatus, Project, SourceRevision, User
from app.projects.service import (
    DuplicateProjectName,
    ProjectBusy,
    ProjectNotFound,
    add_revision,
    create_project,
    delete_project,
    rename_project,
)


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # SQLite 는 외래키 강제가 기본으로 꺼져 있다. 켜지 않으면 ON DELETE CASCADE
    # 가 아예 발동하지 않아, 잡이 남아 있는데도 테스트가 통과하는 허구를 본다.
    # 운영은 Postgres 라 항상 강제된다.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def owner(db):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    await db.commit()
    return user


@pytest.fixture
async def other(db):
    user = User(email="b@example.com", password_hash="x")
    db.add(user)
    await db.commit()
    return user


async def _job(db, project, status: JobStatus) -> Job:
    revision = await add_revision(db, project, "init boron conc=1e15\n")
    job = Job(
        owner_id=project.owner_id,
        source_revision_id=revision.id,
        status=status,
        workdir="/tmp/nowhere",
    )
    db.add(job)
    await db.commit()
    return job


class TestRename:
    async def test_changes_the_name(self, db, owner):
        project = await create_project(db, owner.id, "옛 이름")

        renamed = await rename_project(db, project.id, owner.id, "새 이름")

        assert renamed.name == "새 이름"

    async def test_persists(self, db, owner):
        project = await create_project(db, owner.id, "옛 이름")

        await rename_project(db, project.id, owner.id, "새 이름")

        assert (await db.get(Project, project.id)).name == "새 이름"

    async def test_keeps_revisions(self, db, owner):
        """이름만 바뀐다. 소스가 날아가면 이름 고치기가 위험한 일이 된다."""
        project = await create_project(db, owner.id, "p")
        await add_revision(db, project, "init boron conc=1e15\n")

        await rename_project(db, project.id, owner.id, "q")

        revisions = await db.scalars(
            select(SourceRevision).where(SourceRevision.project_id == project.id)
        )
        assert len(list(revisions)) == 1

    async def test_rejects_a_name_already_taken(self, db, owner):
        await create_project(db, owner.id, "이미 있음")
        project = await create_project(db, owner.id, "고칠 것")

        with pytest.raises(DuplicateProjectName):
            await rename_project(db, project.id, owner.id, "이미 있음")

    async def test_allows_renaming_to_itself(self, db, owner):
        # 자기 이름과 부딪힌다고 거절하면 사용자는 영문을 모른다.
        project = await create_project(db, owner.id, "그대로")

        renamed = await rename_project(db, project.id, owner.id, "그대로")

        assert renamed.name == "그대로"

    async def test_other_users_may_hold_the_same_name(self, db, owner, other):
        # 이름은 사용자 안에서만 유일하다.
        await create_project(db, other.id, "공통")
        project = await create_project(db, owner.id, "내 것")

        renamed = await rename_project(db, project.id, owner.id, "공통")

        assert renamed.name == "공통"

    async def test_refuses_someone_elses_project(self, db, owner, other):
        project = await create_project(db, owner.id, "남의 것")

        with pytest.raises(ProjectNotFound):
            await rename_project(db, project.id, other.id, "가로채기")

    async def test_unknown_project_raises(self, db, owner):
        with pytest.raises(ProjectNotFound):
            await rename_project(db, 9999, owner.id, "없음")


class TestDelete:
    async def test_removes_the_project(self, db, owner):
        project = await create_project(db, owner.id, "지울 것")

        await delete_project(db, project.id, owner.id)

        assert await db.get(Project, project.id) is None

    async def test_takes_revisions_with_it(self, db, owner):
        # 남기면 어느 프로젝트에도 속하지 않는 리비전이 쌓인다.
        project = await create_project(db, owner.id, "지울 것")
        await add_revision(db, project, "init boron conc=1e15\n")

        await delete_project(db, project.id, owner.id)

        remaining = await db.scalars(
            select(SourceRevision).where(SourceRevision.project_id == project.id)
        )
        assert list(remaining) == []

    async def test_takes_finished_jobs_with_it(self, db, owner):
        project = await create_project(db, owner.id, "지울 것")
        job = await _job(db, project, JobStatus.SUCCEEDED)

        await delete_project(db, project.id, owner.id)

        assert await db.get(Job, job.id) is None

    async def test_reports_the_workdirs_it_orphaned(self, db, owner):
        """디스크의 작업 디렉토리는 DB 가 지워 주지 않는다.

        경로를 돌려주지 않으면 호출자가 지울 수 없어 산출물이 영영 남는다.
        """
        project = await create_project(db, owner.id, "지울 것")
        await _job(db, project, JobStatus.SUCCEEDED)

        removed = await delete_project(db, project.id, owner.id)

        assert removed == ("/tmp/nowhere",)

    @pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.RUNNING])
    async def test_refuses_while_a_job_is_live(self, db, owner, status):
        """워커가 집어간 잡의 행이 사라지면 결과를 쓸 곳이 없어진다."""
        project = await create_project(db, owner.id, "돌고 있음")
        await _job(db, project, status)

        with pytest.raises(ProjectBusy):
            await delete_project(db, project.id, owner.id)

    async def test_keeps_everything_when_it_refuses(self, db, owner):
        project = await create_project(db, owner.id, "돌고 있음")
        await _job(db, project, JobStatus.RUNNING)

        with pytest.raises(ProjectBusy):
            await delete_project(db, project.id, owner.id)

        assert await db.get(Project, project.id) is not None

    async def test_finished_jobs_do_not_block(self, db, owner):
        project = await create_project(db, owner.id, "끝남")
        await _job(db, project, JobStatus.FAILED)

        await delete_project(db, project.id, owner.id)

        assert await db.get(Project, project.id) is None

    async def test_refuses_someone_elses_project(self, db, owner, other):
        project = await create_project(db, owner.id, "남의 것")

        with pytest.raises(ProjectNotFound):
            await delete_project(db, project.id, other.id)

        assert await db.get(Project, project.id) is not None

    async def test_frees_the_name(self, db, owner):
        # 지운 이름을 다시 못 쓰면 삭제가 반쪽이 된다.
        project = await create_project(db, owner.id, "재사용")
        await delete_project(db, project.id, owner.id)

        again = await create_project(db, owner.id, "재사용")

        assert again.name == "재사용"
