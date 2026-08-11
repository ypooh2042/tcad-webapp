"""카탈로그 API.

에디터의 자동완성과 진단이 이 엔드포인트에 물린다. 그래서 여기서 내놓는 이름은
**시뮬레이터가 실제로 받아들이는 이름**이어야 한다. 문서에 적힌 원형을 내놓으면
자동완성이 실행되지 않는 코드를 만들어 준다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import routes_catalog

pytestmark = pytest.mark.integration


@pytest.fixture
async def client():
    app = FastAPI()
    app.include_router(routes_catalog.router, prefix="/api")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


class TestNoAuthenticationRequired:
    """카탈로그는 레포에 들어 있는 오픈소스 정의 파일에서 나온 공개 자료다.

    로그인을 요구하면 로그인 화면에서 문법 도움말을 못 쓰고, nginx 가 캐시할
    수도 없다. 사용자 데이터가 전혀 섞이지 않으므로 열어 둔다.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "/api/catalog/commands",
            "/api/catalog/commands/structure",
            "/api/catalog/resolve?token=stru",
            "/api/catalog/complete?prefix=st",
        ],
    )
    async def test_anonymous_access_is_allowed(self, client, path) -> None:
        assert (await client.get(path)).status_code == 200


class TestCommandList:
    async def test_lists_every_card(self, client) -> None:
        body = (await client.get("/api/catalog/commands")).json()

        assert len(body["commands"]) == 45

    async def test_includes_interpreter_keywords(self, client) -> None:
        """source·foreach 는 suprem.key 에 없다. 카드만 내놓으면 사용자는
        가장 기본적인 단어를 자동완성에서 찾지 못한다."""
        body = (await client.get("/api/catalog/commands")).json()

        assert "source" in [k["name"] for k in body["keywords"]]

    async def test_summary_does_not_carry_parameters(self, client) -> None:
        """1175개 파라미터를 목록에 실으면 300KB 가 넘는다."""
        body = (await client.get("/api/catalog/commands")).json()

        assert "parameters" not in body["commands"][0]


class TestCommandDetail:
    async def test_returns_parameters(self, client) -> None:
        body = (await client.get("/api/catalog/commands/initialize")).json()
        names = [p["name"] for p in body["parameters"]]

        assert "conc" in names

    async def test_resolves_a_prefix(self, client) -> None:
        """사용자가 친 그대로 넘어온다. stru 도 structure 로 찾아야 한다."""
        body = (await client.get("/api/catalog/commands/stru")).json()

        assert body["name"] == "structure"

    async def test_ambiguous_prefix_is_a_client_error(self, client) -> None:
        response = await client.get("/api/catalog/commands/str")

        assert response.status_code == 409
        assert set(response.json()["detail"]["candidates"]) == {
            "stress",
            "structure",
        }

    async def test_unknown_command_is_404(self, client) -> None:
        assert (await client.get("/api/catalog/commands/zzzzz")).status_code == 404

    async def test_uppercase_is_not_found(self, client) -> None:
        assert (
            await client.get("/api/catalog/commands/STRUCTURE")
        ).status_code == 404

    async def test_exposes_the_original_name_when_truncated(self, client) -> None:
        body = (await client.get("/api/catalog/commands/deposit")).json()
        param = next(
            p for p in body["parameters"] if p["name"] == "concentrati"
        )

        assert param["source_name"] == "concentration"
        assert param["truncated"] is True

    async def test_marks_unreachable_parameters(self, client) -> None:
        body = (await client.get("/api/catalog/commands/structure")).json()
        backside = next(p for p in body["parameters"] if p["name"] == "backside")

        assert backside["unreachable"] is True

    async def test_carries_switch_groups(self, client) -> None:
        body = (await client.get("/api/catalog/commands/initialize")).json()
        boron = next(p for p in body["parameters"] if p["name"] == "boron")

        assert boron["group"] == "impurity"


class TestResolve:
    @pytest.mark.parametrize(
        ("token", "kind", "name"),
        [
            ("stru", "command", "structure"),
            ("structure", "command", "structure"),
            ("source", "keyword", "source"),
            ("set", "keyword", "set"),
        ],
    )
    async def test_reports_what_a_word_becomes(
        self, client, token, kind, name
    ) -> None:
        body = (await client.get(f"/api/catalog/resolve?token={token}")).json()

        assert body["kind"] == kind
        assert body["name"] == name

    async def test_reports_ambiguity_with_candidates(self, client) -> None:
        body = (await client.get("/api/catalog/resolve?token=str")).json()

        assert body["kind"] == "ambiguous"
        assert set(body["candidates"]) == {"stress", "structure"}

    async def test_reports_shell_fallthrough(self, client) -> None:
        """인식되지 않는 단어는 조용히 /bin/bash 로 넘어간다. 오타가 오류 없이
        지나가므로 에디터가 이걸 경고해 줘야 한다."""
        body = (await client.get("/api/catalog/resolve?token=zzzzz")).json()

        assert body["kind"] == "unknown"

    async def test_shortened_keyword_is_not_a_keyword(self, client) -> None:
        body = (await client.get("/api/catalog/resolve?token=sourc")).json()

        assert body["kind"] != "keyword"

    async def test_empty_token_is_rejected(self, client) -> None:
        assert (await client.get("/api/catalog/resolve?token=")).status_code == 422


class TestCompletion:
    async def test_completes_commands(self, client) -> None:
        body = (await client.get("/api/catalog/complete?prefix=sel")).json()
        names = [c["name"] for c in body["completions"]]

        assert set(names) == {"select", "selenium"}

    async def test_completes_keywords_too(self, client) -> None:
        body = (await client.get("/api/catalog/complete?prefix=sou")).json()

        assert "source" in [c["name"] for c in body["completions"]]

    async def test_completes_parameters_within_a_command(self, client) -> None:
        body = (
            await client.get("/api/catalog/complete?prefix=co&command=initialize")
        ).json()
        names = [c["name"] for c in body["completions"]]

        assert "conc" in names

    async def test_omits_unreachable_parameters(self, client) -> None:
        """골라 봐야 시뮬레이터가 ambiguous 로 거절한다."""
        body = (
            await client.get(
                "/api/catalog/complete?prefix=backside&command=structure"
            )
        ).json()
        names = [c["name"] for c in body["completions"]]

        assert names == ["backside.y"]

    async def test_unknown_command_is_404(self, client) -> None:
        response = await client.get(
            "/api/catalog/complete?prefix=x&command=zzzzz"
        )

        assert response.status_code == 404

    async def test_empty_prefix_lists_everything(self, client) -> None:
        body = (await client.get("/api/catalog/complete?prefix=")).json()

        assert len(body["completions"]) == 45 + 15
