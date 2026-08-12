"""사용자 작업공간의 경로 해석.

**이 모듈이 뚫리면 서버 파일시스템 전체가 열린다.** 사용자가 보내는 경로는
전부 신뢰할 수 없는 입력이므로, 자기 루트 밖으로 나가는 모든 형태를 막아야
한다 — `..`, 절대경로, 심볼릭 링크, 널 바이트.

사용자에게 보이는 경로는 항상 루트 기준 상대경로다. 서버의 실제 절대경로는
화면에도 오류 메시지에도 나타나지 않는다.
"""

from __future__ import annotations

import pytest

from app.workspace.paths import (
    InvalidPath,
    OUTSIDE_ROOT,
    is_source_file,
    relative_to_root,
    resolve_in_root,
    validate_name,
)


@pytest.fixture
def root(tmp_path):
    home = tmp_path / "user-1"
    home.mkdir()
    return home


class TestResolve:
    def test_accepts_a_plain_name(self, root):
        assert resolve_in_root(root, "boron.in") == root / "boron.in"

    def test_accepts_a_nested_path(self, root):
        assert resolve_in_root(root, "semi/boron.in") == root / "semi" / "boron.in"

    def test_root_itself_is_the_empty_path(self, root):
        assert resolve_in_root(root, "") == root

    def test_normalises_redundant_separators(self, root):
        assert resolve_in_root(root, "semi//boron.in") == root / "semi" / "boron.in"

    def test_normalises_dot_segments(self, root):
        assert resolve_in_root(root, "./semi/./boron.in") == root / "semi" / "boron.in"

    def test_inner_parent_segment_is_resolved(self, root):
        # semi/../boron.in 은 루트 안이므로 허용된다.
        assert resolve_in_root(root, "semi/../boron.in") == root / "boron.in"


class TestEscapes:
    @pytest.mark.parametrize(
        "path",
        [
            "..",
            "../etc/passwd",
            "semi/../../etc/passwd",
            "a/b/../../../outside.in",
        ],
    )
    def test_rejects_climbing_out(self, root, path):
        with pytest.raises(InvalidPath):
            resolve_in_root(root, path)

    @pytest.mark.parametrize("path", ["/etc/passwd", "/", "//etc/passwd"])
    def test_rejects_absolute_paths(self, root, path):
        with pytest.raises(InvalidPath):
            resolve_in_root(root, path)

    def test_rejects_null_bytes(self, root):
        # 널 바이트는 C 계층에서 경로를 잘라 검사를 통과시킬 수 있다.
        with pytest.raises(InvalidPath):
            resolve_in_root(root, "boron.in\x00.txt")

    def test_rejects_a_symlink_pointing_outside(self, root, tmp_path):
        """심볼릭 링크는 문자열 검사를 그대로 통과한다. 실제로 따라가 봐야 한다."""
        outside = tmp_path / "secret.in"
        outside.write_text("비밀")
        (root / "link.in").symlink_to(outside)

        with pytest.raises(InvalidPath):
            resolve_in_root(root, "link.in")

    def test_rejects_a_path_through_a_symlinked_folder(self, root, tmp_path):
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        (outside / "x.in").write_text("비밀")
        (root / "hop").symlink_to(outside)

        with pytest.raises(InvalidPath):
            resolve_in_root(root, "hop/x.in")

    def test_error_never_leaks_the_server_path(self, root):
        # 오류 메시지에 절대경로가 섞이면 서버 구조가 드러난다.
        with pytest.raises(InvalidPath) as caught:
            resolve_in_root(root, "../../etc/passwd")

        assert str(root) not in str(caught.value)
        assert str(caught.value) == OUTSIDE_ROOT


class TestRelative:
    def test_gives_a_root_relative_path(self, root):
        assert relative_to_root(root, root / "semi" / "boron.in") == "semi/boron.in"

    def test_root_itself_is_empty(self, root):
        assert relative_to_root(root, root) == ""

    def test_uses_forward_slashes(self, root):
        # 화면에 그대로 뿌린다. OS 구분자가 새면 사용자마다 다르게 보인다.
        assert "/" in relative_to_root(root, root / "a" / "b.in")


class TestNames:
    @pytest.mark.parametrize("name", ["boron.in", "step1.in", "a-b_c.in", "폴더"])
    def test_accepts_ordinary_names(self, name):
        validate_name(name)

    @pytest.mark.parametrize(
        "name",
        ["", ".", "..", "a/b", "a\\b", "a\x00b", " ", "  "],
    )
    def test_rejects_broken_names(self, name):
        with pytest.raises(InvalidPath):
            validate_name(name)

    def test_rejects_names_that_are_too_long(self):
        with pytest.raises(InvalidPath):
            validate_name("a" * 256)

    def test_rejects_leading_dot(self):
        # 숨김 파일은 목록에 안 보이는데 용량은 차지한다.
        with pytest.raises(InvalidPath):
            validate_name(".hidden.in")


class TestSourceFile:
    @pytest.mark.parametrize("name", ["a.in", "semi/b.in", "A.IN"])
    def test_recognises_source_files(self, name):
        assert is_source_file(name)

    @pytest.mark.parametrize(
        "name", ["a.str", "a.txt", "a", "a.in.txt", "a.png"]
    )
    def test_rejects_everything_else(self, name):
        # `.in` 과 폴더만 보이고 만들 수 있다.
        assert not is_source_file(name)
