"""매뉴얼 API.

카탈로그와 같은 이유로 공개다 — 1993년 매뉴얼에서 나온 자료이고 사용자 데이터가
섞이지 않는다.
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


class TestNoAuthenticationRequired:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/docs/sections",
            "/api/docs/sections/implant",
            "/api/docs/for-command/stru",
            "/api/docs/search?q=oxidation",
        ],
    )
    async def test_anonymous_access_is_allowed(self, client, path) -> None:
        assert (await client.get(path)).status_code == 200


class TestSections:
    async def test_lists_every_section(self, client) -> None:
        body = (await client.get("/api/docs/sections")).json()

        assert len(body) == 78

    async def test_filters_by_kind(self, client) -> None:
        body = (await client.get("/api/docs/sections?kind=command")).json()

        assert len(body) == 50
        assert all(s["kind"] == "command" for s in body)

    async def test_summary_omits_the_body(self, client) -> None:
        """전부 합치면 332KB 다. 목록에서는 필요 없다."""
        body = (await client.get("/api/docs/sections")).json()

        assert "subsections" not in body[0]

    async def test_detail_has_the_body(self, client) -> None:
        body = (await client.get("/api/docs/sections/implant")).json()

        assert "SYNOPSIS" in body["subsections"]
        assert "DESCRIPTION" in body["subsections"]

    async def test_detail_carries_page_numbers(self, client) -> None:
        body = (await client.get("/api/docs/sections/implant")).json()

        assert body["pdf_page_start"] > 0

    async def test_unknown_section_is_404(self, client) -> None:
        assert (await client.get("/api/docs/sections/zzz")).status_code == 404


class TestForCommand:
    async def test_finds_by_full_name(self, client) -> None:
        body = (await client.get("/api/docs/for-command/implant")).json()

        assert body["command"] == "implant"

    async def test_resolves_a_prefix(self, client) -> None:
        """사용자는 `stru` 라고 친다. 시뮬레이터가 그렇게 해석하기 때문이다."""
        body = (await client.get("/api/docs/for-command/stru")).json()

        assert body["command"] == "structure"

    async def test_ambiguous_prefix_is_404(self, client) -> None:
        """`str` 은 stress 와 structure 사이에서 모호하다. 시뮬레이터도 거절한다."""
        assert (await client.get("/api/docs/for-command/str")).status_code == 404

    async def test_uppercase_is_404(self, client) -> None:
        assert (
            await client.get("/api/docs/for-command/IMPLANT")
        ).status_code == 404


class TestSearch:
    async def test_finds_sections(self, client) -> None:
        body = (await client.get("/api/docs/search?q=oxidation")).json()

        assert body["hits"]

    async def test_ranks_the_command_page_first(self, client) -> None:
        body = (await client.get("/api/docs/search?q=implant")).json()

        assert body["hits"][0]["command"] == "implant"

    async def test_returns_snippets(self, client) -> None:
        body = (await client.get("/api/docs/search?q=oxidation")).json()

        assert body["hits"][0]["snippet"]

    async def test_respects_the_limit(self, client) -> None:
        body = (await client.get("/api/docs/search?q=the&limit=3")).json()

        assert len(body["hits"]) <= 3

    async def test_single_character_is_rejected(self, client) -> None:
        """한 글자는 거의 모든 섹션에 걸려 결과가 의미를 잃는다."""
        assert (await client.get("/api/docs/search?q=a")).status_code == 422

    async def test_no_match_is_an_empty_list(self, client) -> None:
        body = (await client.get("/api/docs/search?q=zzzznotinmanual")).json()

        assert body["hits"] == []
