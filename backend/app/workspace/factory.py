"""사용자별 작업공간 배정.

루트 이름에는 **id 만** 쓴다. 이메일을 쓰면 서버 디렉토리 목록에 사용자 신원이
그대로 남는다.
"""

from __future__ import annotations

from app.core.config import Settings
from app.workspace.service import Workspace

_MEGABYTE = 1024 * 1024


def workspace_for(settings: Settings, user_id: int, is_admin: bool) -> Workspace:
    """이 사용자의 작업공간. 상한은 역할에 따라 다르다."""
    quota_mb = (
        settings.admin_workspace_quota_mb if is_admin else settings.workspace_quota_mb
    )
    return Workspace(
        root=settings.workspaces_root / f"user-{user_id}",
        quota_bytes=quota_mb * _MEGABYTE,
    )
