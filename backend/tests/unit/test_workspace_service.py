"""작업공간 파일 조작.

사용자에게는 자기 루트가 파일시스템 전부로 보인다. **폴더와 `.in` 파일만**
보이고 만들 수 있다 — `.str` 은 실행 결과라 여기서 다루지 않고, 그 밖의 것은
애초에 만들 수 없다.

용량 상한은 소스 파일에만 건다. 산출물(`.str`)은 캐시로 따로 관리한다.
"""

from __future__ import annotations

import pytest

from app.workspace.paths import InvalidPath
from app.workspace.service import (
    QuotaExceeded,
    Workspace,
    WorkspaceConflict,
    WorkspaceNotFound,
)


def empty_workspace(root, quota_bytes=1024 * 1024) -> Workspace:
    """예제가 들어 있지 않은 작업공간.

    새 작업공간에는 예제가 한 개 들어간다(app/workspace/starter.py). 여기서
    보려는 것은 파일 조작 자체이므로, 루트를 미리 만들어 씨앗 뿌리기를
    건너뛴다 — 씨앗 자체는 test_workspace_starter.py 가 본다.
    """
    root.mkdir(parents=True, exist_ok=True)
    return Workspace(root=root, quota_bytes=quota_bytes)


@pytest.fixture
def workspace(tmp_path):
    return empty_workspace(tmp_path / "user-1")


class TestSetup:
    def test_creates_the_root_on_demand(self, tmp_path):
        # 가입 직후 첫 요청에서 루트가 없으면 목록부터 실패한다.
        fresh = Workspace(root=tmp_path / "user-1", quota_bytes=1024 * 1024)

        assert [entry.name for entry in fresh.list()] == ["nmos.in"]
        assert fresh.root.is_dir()


class TestWrite:
    def test_creates_a_source_file(self, workspace):
        workspace.write("boron.in", "init boron conc=1e15\n")

        assert workspace.read("boron.in") == "init boron conc=1e15\n"

    def test_overwrites_an_existing_file(self, workspace):
        workspace.write("boron.in", "옛 내용")

        workspace.write("boron.in", "새 내용")

        assert workspace.read("boron.in") == "새 내용"

    def test_creates_parent_folders_that_exist(self, workspace):
        workspace.make_folder("semi")

        workspace.write("semi/boron.in", "x")

        assert workspace.read("semi/boron.in") == "x"

    def test_refuses_a_missing_parent(self, workspace):
        # 조용히 폴더를 만들어 주면 오타로 엉뚱한 트리가 생긴다.
        with pytest.raises(WorkspaceNotFound):
            workspace.write("없는폴더/boron.in", "x")

    @pytest.mark.parametrize("name", ["a.str", "a.txt", "a", "a.png"])
    def test_refuses_anything_but_source_files(self, workspace, name):
        with pytest.raises(InvalidPath):
            workspace.write(name, "x")

    def test_refuses_writing_onto_a_folder(self, workspace):
        # 폴더 이름에도 .in 을 붙일 수 있어서 실제로 부딪힌다.
        workspace.make_folder("boron.in")

        with pytest.raises(WorkspaceConflict):
            workspace.write("boron.in", "x")


class TestRead:
    def test_missing_file_raises(self, workspace):
        with pytest.raises(WorkspaceNotFound):
            workspace.read("없다.in")

    def test_reading_a_folder_raises(self, workspace):
        workspace.make_folder("semi")

        with pytest.raises(WorkspaceNotFound):
            workspace.read("semi")


class TestFolders:
    def test_creates_a_folder(self, workspace):
        workspace.make_folder("semi")

        assert [entry.path for entry in workspace.list()] == ["semi"]

    def test_creates_a_nested_folder(self, workspace):
        workspace.make_folder("semi")
        workspace.make_folder("semi/deep")

        assert workspace.read_dir("semi")[0].path == "semi/deep"

    def test_refuses_a_duplicate(self, workspace):
        workspace.make_folder("semi")

        with pytest.raises(WorkspaceConflict):
            workspace.make_folder("semi")

    def test_refuses_a_missing_parent(self, workspace):
        with pytest.raises(WorkspaceNotFound):
            workspace.make_folder("없는곳/deep")


class TestListing:
    def test_hides_everything_but_folders_and_sources(self, workspace):
        workspace.write("keep.in", "x")
        workspace.make_folder("semi")
        # 실행 결과와 잡동사니는 보이지 않아야 한다.
        (workspace.root / "result.str").write_text("x")
        (workspace.root / "notes.txt").write_text("x")
        (workspace.root / ".hidden").write_text("x")

        assert sorted(entry.path for entry in workspace.list()) == [
            "keep.in",
            "semi",
        ]

    def test_folders_come_first(self, workspace):
        # 트리를 훑을 때 폴더가 섞여 있으면 구조가 눈에 안 들어온다.
        workspace.write("a.in", "x")
        workspace.make_folder("z")

        assert [entry.path for entry in workspace.list()] == ["z", "a.in"]

    def test_marks_folders(self, workspace):
        workspace.make_folder("semi")

        assert workspace.list()[0].is_dir is True

    def test_reports_file_size(self, workspace):
        workspace.write("a.in", "12345")

        assert workspace.read_dir("")[0].size_bytes == 5

    def test_lists_a_subfolder(self, workspace):
        workspace.make_folder("semi")
        workspace.write("semi/b.in", "x")

        assert [entry.path for entry in workspace.read_dir("semi")] == ["semi/b.in"]

    def test_full_tree_walks_every_level(self, workspace):
        workspace.make_folder("semi")
        workspace.write("semi/b.in", "x")
        workspace.write("a.in", "x")

        assert sorted(entry.path for entry in workspace.tree()) == [
            "a.in",
            "semi",
            "semi/b.in",
        ]


class TestRename:
    def test_renames_a_file(self, workspace):
        workspace.write("old.in", "내용")

        workspace.rename("old.in", "new.in")

        assert workspace.read("new.in") == "내용"

    def test_moves_into_a_folder(self, workspace):
        # 이름 바꾸기와 옮기기를 한 연산으로 쓴다.
        workspace.write("a.in", "내용")
        workspace.make_folder("semi")

        workspace.rename("a.in", "semi/a.in")

        assert workspace.read("semi/a.in") == "내용"

    def test_renames_a_folder_with_contents(self, workspace):
        workspace.make_folder("old")
        workspace.write("old/a.in", "내용")

        workspace.rename("old", "new")

        assert workspace.read("new/a.in") == "내용"

    def test_refuses_to_clobber(self, workspace):
        workspace.write("a.in", "A")
        workspace.write("b.in", "B")

        with pytest.raises(WorkspaceConflict):
            workspace.rename("a.in", "b.in")

        assert workspace.read("b.in") == "B"

    def test_refuses_changing_a_source_into_something_else(self, workspace):
        # `.txt` 로 바꾸면 목록에서 사라져 되찾을 길이 없어진다.
        workspace.write("a.in", "x")

        with pytest.raises(InvalidPath):
            workspace.rename("a.in", "a.txt")

    def test_missing_source_raises(self, workspace):
        with pytest.raises(WorkspaceNotFound):
            workspace.rename("없다.in", "b.in")

    def test_refuses_moving_a_folder_into_itself(self, workspace):
        # 허용하면 트리가 끊겨 되돌릴 수 없다.
        workspace.make_folder("a")
        workspace.make_folder("a/b")

        with pytest.raises(WorkspaceConflict):
            workspace.rename("a", "a/b/a")


class TestDelete:
    def test_deletes_a_file(self, workspace):
        workspace.write("a.in", "x")

        workspace.delete("a.in")

        assert workspace.list() == []

    def test_deletes_a_folder_and_its_contents(self, workspace):
        workspace.make_folder("semi")
        workspace.write("semi/a.in", "x")

        workspace.delete("semi")

        assert workspace.list() == []

    def test_missing_target_raises(self, workspace):
        with pytest.raises(WorkspaceNotFound):
            workspace.delete("없다.in")

    def test_refuses_to_delete_the_root(self, workspace):
        workspace.write("a.in", "x")

        with pytest.raises(InvalidPath):
            workspace.delete("")

        assert workspace.read("a.in") == "x"


class TestQuota:
    def test_reports_usage(self, workspace):
        workspace.write("a.in", "12345")

        assert workspace.usage().used_bytes == 5

    def test_reports_the_limit(self, workspace):
        assert workspace.usage().quota_bytes == 1024 * 1024

    def test_refuses_a_write_that_would_exceed(self, tmp_path):
        small = empty_workspace(tmp_path / "u", quota_bytes=10)

        with pytest.raises(QuotaExceeded):
            small.write("a.in", "x" * 11)

    def test_the_rejected_write_leaves_nothing_behind(self, tmp_path):
        # 반쯤 쓰다 실패하면 상한을 넘긴 채로 남는다.
        small = empty_workspace(tmp_path / "u", quota_bytes=10)

        with pytest.raises(QuotaExceeded):
            small.write("a.in", "x" * 11)

        assert small.list() == []

    def test_overwriting_counts_only_the_difference(self, tmp_path):
        """기존 파일을 덮어쓸 때 옛 크기를 빼지 않으면, 상한 가까이에서
        같은 파일을 저장하는 것조차 막힌다."""
        small = empty_workspace(tmp_path / "u", quota_bytes=10)
        small.write("a.in", "x" * 9)

        small.write("a.in", "y" * 10)

        assert small.read("a.in") == "y" * 10

    def test_source_files_only(self, workspace):
        # 산출물은 캐시로 따로 관리한다. 여기 셈에 넣으면 실행할수록 저장이 막힌다.
        (workspace.root).mkdir(parents=True, exist_ok=True)
        (workspace.root / "big.str").write_text("x" * 5000)
        workspace.write("a.in", "12345")

        assert workspace.usage().used_bytes == 5
