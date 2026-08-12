"""레퍼런스 엔드포인트.

목록은 **가볍게** 내려야 한다. 커맨드 하나하나에 산문과 파라미터까지 실으면
800KB 가 되어, 패널을 여는 것만으로 그만큼을 받는다. 목록에는 고르는 데 필요한
것만 담고 본문은 고른 뒤에 따로 읽는다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import routes_docs

pytestmark = pytest.mark.integration


@pytest.fixture
async def client():
    app = FastAPI()
    app.include_router(routes_docs.router, prefix="/api")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


class TestIndex:
    async def test_lists_groups_in_manual_order(self, client):
        response = await client.get("/api/docs/reference")

        assert response.status_code == 200
        names = [group["name"] for group in response.json()["groups"]]
        # 데이터를 넣고, 공정을 돌리고, 결과를 본다 — 매뉴얼이 세운 순서다.
        assert names[:3] == ["데이터 입출력", "공정 시뮬레이션", "결과 보기"]

    async def test_each_group_carries_its_commands(self, client):
        response = await client.get("/api/docs/reference")

        groups = {g["name"]: g for g in response.json()["groups"]}
        assert "implant" in [c["name"] for c in groups["공정 시뮬레이션"]["commands"]]

    async def test_each_command_carries_a_summary(self, client):
        """요약이 없으면 목록이 이름 나열에 그친다 — 무엇을 고를지 알 수 없다."""
        response = await client.get("/api/docs/reference")

        implant = _find(response.json(), "implant")
        assert implant["summary"] == "Perform ion implantation."

    async def test_reports_parameter_count(self, client):
        # 몇 개를 받는 커맨드인지 미리 보이면 마음의 준비가 된다.
        response = await client.get("/api/docs/reference")

        assert _find(response.json(), "implant")["parameter_count"] > 0

    async def test_links_to_the_manual_section(self, client):
        response = await client.get("/api/docs/reference")

        assert _find(response.json(), "implant")["manual_section_id"]

    async def test_marks_undocumented_commands(self, client):
        # suprem.key 에는 있는데 매뉴얼에 설명이 없다. 빼면 존재를 모른다.
        response = await client.get("/api/docs/reference")

        device = _find(response.json(), "device")
        assert device["documented"] is False
        assert device["manual_section_id"] is None

    async def test_does_not_ship_the_prose(self, client):
        """본문까지 실으면 800KB 다. 목록을 여는 것만으로 받으면 안 된다."""
        response = await client.get("/api/docs/reference")

        implant = _find(response.json(), "implant")
        assert "description" not in implant
        assert "parameters" not in implant

    async def test_stays_small(self, client):
        response = await client.get("/api/docs/reference")

        assert len(response.content) < 32_000

    async def test_needs_no_login(self, client):
        """카탈로그와 같은 이유다 — 1993년 공개 매뉴얼이고 사용자 데이터가
        섞이지 않는다. 로그인 화면에서도 찾아볼 수 있어야 한다."""
        response = await client.get("/api/docs/reference")

        assert response.status_code == 200


def _find(payload: dict, name: str) -> dict:
    for group in payload["groups"]:
        for command in group["commands"]:
            if command["name"] == name:
                return command
    raise AssertionError(f"{name} 이 목록에 없다")
