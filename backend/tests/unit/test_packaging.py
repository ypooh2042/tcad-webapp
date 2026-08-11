"""패키징이 새 환경에서 실제로 설치·임포트되는지.

개발 환경은 오래 쓰면서 이것저것 들어와 있어서, 선언하지 않은 의존성도 그냥
동작한다. 그래서 **새로 설치한 서버에서만** 터진다. 배포 리허설에서 두 번 겪었다:

  1. `pip install -e .` 자체가 실패했다. pyproject 에 패키지 선언이 없어서
     setuptools 가 alembic(마이그레이션 스크립트)과 var(런타임 산출물)까지
     패키지 후보로 보고 "Multiple top-level packages discovered" 로 멈췄다.
     alembic 을 추가한 시점부터 깨져 있었는데, 개발 환경은 그 전에 설치해 둔
     상태라 드러나지 않았다.

  2. 설치는 됐는데 앱이 임포트 단계에서 죽었다. EmailStr 이 email-validator 를
     필요로 하는데 의존성에 없었다. 서비스가 아예 뜨지 못한다.

여기서는 선언 내용을 검사한다. 실제 새 venv 설치는 느려서 매번 돌릴 수 없다.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text())


class TestPackageDiscovery:
    def test_packages_are_declared_explicitly(self, pyproject) -> None:
        """자동 탐색에 맡기면 최상위 디렉토리가 늘어날 때마다 설치가 깨진다."""
        find = pyproject["tool"]["setuptools"]["packages"]["find"]

        assert find["include"] == ["app*"]

    def test_migration_directory_is_not_a_package(self) -> None:
        """alembic 은 마이그레이션 스크립트지 임포트할 패키지가 아니다."""
        assert (BACKEND_ROOT / "alembic").is_dir()
        assert not (BACKEND_ROOT / "alembic" / "__init__.py").exists()


@pytest.fixture(scope="module")
def declared(pyproject) -> str:
    return " ".join(pyproject["project"]["dependencies"]).lower()


class TestRuntimeDependencies:
    """앱이 임포트하는 것은 전부 선언돼 있어야 한다."""

    def test_email_validator_is_declared(self, declared) -> None:
        """EmailStr 이 이걸 요구한다. 빼면 앱이 임포트 단계에서 죽는다."""
        assert "pydantic[email]" in declared or "email-validator" in declared

    @pytest.mark.parametrize(
        "package",
        [
            "fastapi",
            "uvicorn",
            "pydantic-settings",
            "sqlalchemy",
            "asyncpg",
            "alembic",
            "redis",
            "argon2-cffi",
        ],
    )
    def test_core_dependency_is_declared(self, declared, package) -> None:
        assert package in declared

    def test_dev_only_tools_are_not_runtime_dependencies(self, declared) -> None:
        """pytest 같은 것이 런타임에 끼면 배포본이 쓸데없이 무거워진다."""
        for tool in ("pytest", "httpx", "aiosqlite"):
            assert tool not in declared


class TestRuntimeArtifactsAreNotShipped:
    def test_var_is_not_tracked(self) -> None:
        """var 은 런타임 산출물이다. 커밋되면 배포본에 옛 잡이 따라간다."""
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files", "backend/var"],
            cwd=BACKEND_ROOT.parent,
            capture_output=True,
            text=True,
        ).stdout.strip()

        assert tracked == ""
