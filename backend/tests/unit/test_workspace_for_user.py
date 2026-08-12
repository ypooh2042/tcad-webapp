"""사용자별 작업공간 배정.

상한은 역할에 따라 다르다. 관리자는 예제와 참고 자료를 쌓아 둘 여지가 필요하다.
"""

from __future__ import annotations

from app.core.config import Settings
from app.workspace.factory import workspace_for


def _settings(tmp_path):
    return Settings(
        workspaces_root=tmp_path,
        workspace_quota_mb=50,
        admin_workspace_quota_mb=1024,
    )


class TestRoot:
    def test_each_user_gets_their_own(self, tmp_path):
        a = workspace_for(_settings(tmp_path), user_id=1, is_admin=False)
        b = workspace_for(_settings(tmp_path), user_id=2, is_admin=False)

        assert a.root != b.root

    def test_root_is_under_the_configured_folder(self, tmp_path):
        space = workspace_for(_settings(tmp_path), user_id=7, is_admin=False)

        assert space.root.parent == tmp_path

    def test_root_name_does_not_leak_the_email(self, tmp_path):
        # 디렉토리 이름은 서버에 남는다. id 만 쓴다.
        space = workspace_for(_settings(tmp_path), user_id=7, is_admin=False)

        assert space.root.name == "user-7"


class TestQuota:
    def test_regular_user_gets_fifty_megabytes(self, tmp_path):
        space = workspace_for(_settings(tmp_path), user_id=1, is_admin=False)

        assert space.quota_bytes == 50 * 1024 * 1024

    def test_admin_gets_a_gigabyte(self, tmp_path):
        space = workspace_for(_settings(tmp_path), user_id=1, is_admin=True)

        assert space.quota_bytes == 1024 * 1024 * 1024
