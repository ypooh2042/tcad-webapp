"""설정.

값은 전부 `TCAD_` 접두 환경변수나 `.env` 로 덮어쓸 수 있다.

기본값은 **개발 편의를 위한 것이며 compose.dev.yml 과 짝을 이룬다.** 따라서
database_url 에는 개발용 비밀번호가 들어 있다. 운영에서는 반드시 환경변수로
덮어써야 하며, 이를 강제하는 것은 배포 설정의 몫이다(코드가 막아주지 않는다).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="TCAD_", extra="ignore"
    )

    #: 개발 기본값은 compose.dev.yml 의 컨테이너를 가리킨다. 운영 값은
    #: TCAD_DATABASE_URL 로 주입하며 절대 커밋하지 않는다.
    database_url: str = "postgresql+asyncpg://tcad:tcad-dev-only@localhost:5433/tcad"
    redis_url: str = "redis://localhost:6380/0"

    #: 잡 스크래치 디렉토리의 부모. 컨테이너에 bind mount 되는 유일한 경로다.
    jobs_root: Path = Path("var/jobs")

    #: 동시에 돌릴 시뮬레이션 수. 6코어 홈서버에서 다른 서비스와 공존해야 하므로
    #: 코어 수보다 넉넉히 낮게 잡는다. 로그인 정원(10명)과는 별개의 값이다.
    max_concurrent_jobs: int = 4

    session_cookie_name: str = "tcad_session"
    #: 운영에서는 반드시 True. HTTPS 로만 쿠키를 보내게 한다.
    session_cookie_secure: bool = True

    sandbox_image: str = "tcad/suprem:latest"
    job_timeout_seconds: int = Field(default=600, gt=0)

    #: 사용자당 저장 가능한 산출물 총량. CMOS 예제 한 번이 약 5MB 다.
    storage_quota_mb: int = Field(default=500, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
