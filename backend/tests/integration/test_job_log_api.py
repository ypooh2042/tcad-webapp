"""잡 로그 전문 내려받기.

화면에 뿌리는 로그에는 상한이 있다(무한 출력을 내는 것이 사용자에게 열려 있다).
잘린 경우에도 원문이 사라지지는 않아야 하므로 전문을 따로 내려받게 한다.

로그에는 사용자가 쓴 코드와 실행 결과가 그대로 들어 있다. 남의 것을 읽히면 안
되고, 존재 여부조차 알려주면 안 된다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import Job, JobStatus
from app.runner.logfile import write_full_log
from tests.integration.test_project_job_api import (  # noqa: F401 - 픽스처 재사용
    alice,
    app,
    bob,
)

pytestmark = pytest.mark.integration

FULL_LOG = "첫 줄\n" + "본문 " * 100_000 + "\n마지막 줄"


async def make_job(app, client, tmp: Path, *, log: str, write_file: bool) -> int:
    """로그가 달린 잡 하나를 직접 넣는다. 실제 실행은 podman 이 필요하다."""
    me = (await client.get("/api/auth/me")).json()
    workdir = tmp / "job-under-test"
    workdir.mkdir(parents=True, exist_ok=True)
    if write_file:
        write_full_log(workdir, log)

    async with app.state.sessionmaker() as db:
        job = Job(
            owner_id=me["id"],
            status=JobStatus.SUCCEEDED,
            workdir=str(workdir),
            log=log[:1000],
            exit_code=0,
        )
        db.add(job)
        await db.commit()
        return job.id


class TestFullLog:
    async def test_owner_gets_the_whole_thing(self, app, alice, tmp_path) -> None:
        """미리보기가 잘려 있어도 전문은 한 글자도 빠지지 않아야 한다."""
        job_id = await make_job(
            app, alice, tmp_path, log=FULL_LOG, write_file=True
        )

        response = await alice.get(f"/api/jobs/{job_id}/log")

        assert response.status_code == 200
        assert response.text == FULL_LOG

    async def test_gone_after_cleanup(self, app, alice, tmp_path) -> None:
        """산출물이 정리되면 작업디렉토리째 사라진다. 500 이 아니라 410 이다."""
        job_id = await make_job(
            app, alice, tmp_path, log=FULL_LOG, write_file=False
        )

        response = await alice.get(f"/api/jobs/{job_id}/log")

        assert response.status_code == 410


class TestIsolation:
    async def test_other_user_cannot_read(self, app, alice, bob, tmp_path) -> None:
        job_id = await make_job(
            app, alice, tmp_path, log=FULL_LOG, write_file=True
        )

        response = await bob.get(f"/api/jobs/{job_id}/log")

        # 403 이면 "그런 잡이 있다"를 알려 주는 셈이다.
        assert response.status_code == 404

    async def test_anonymous_is_rejected(self, app, alice, tmp_path) -> None:
        job_id = await make_job(
            app, alice, tmp_path, log=FULL_LOG, write_file=True
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as anon:
            response = await anon.get(f"/api/jobs/{job_id}/log")

        assert response.status_code == 401


class TestTruncationFlag:
    async def test_detail_reports_truncation(self, app, alice, tmp_path) -> None:
        """화면은 이 값을 보고 전문 내려받기를 안내한다."""
        from app.runner.runner import _truncate_log

        long_log = _truncate_log("x" * 3_000_000)
        me = (await alice.get("/api/auth/me")).json()
        async with app.state.sessionmaker() as db:
            job = Job(
                owner_id=me["id"],
                status=JobStatus.SUCCEEDED,
                workdir=str(tmp_path),
                log=long_log,
            )
            db.add(job)
            await db.commit()
            job_id = job.id

        detail = (await alice.get(f"/api/jobs/{job_id}")).json()

        assert detail["log_truncated"] is True

    async def test_short_log_is_not_flagged(self, app, alice, tmp_path) -> None:
        job_id = await make_job(
            app, alice, tmp_path, log="짧다", write_file=True
        )

        detail = (await alice.get(f"/api/jobs/{job_id}")).json()

        assert detail["log_truncated"] is False
