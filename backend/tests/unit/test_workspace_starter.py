"""새 작업공간에 들어가는 예제 파일.

처음 들어온 사람에게 빈 화면을 주면 무엇부터 해야 할지 알 수 없다. 실제로
도는 예제 하나가 들어 있으면 열어서 실행해 보는 것으로 시작할 수 있다.
"""

from __future__ import annotations

from pathlib import Path

from app.workspace.service import Workspace
from app.workspace.starter import EXAMPLES, seed

REPO_ROOT = Path(__file__).resolve().parents[3]


def workspace(tmp_path: Path) -> Workspace:
    return Workspace(root=tmp_path / "user-1", quota_bytes=50 * 1024 * 1024)


class TestSeeding:
    def test_new_workspace_gets_the_example(self, tmp_path) -> None:
        assert [entry.name for entry in workspace(tmp_path).list()] == ["nmos.in"]

    def test_the_example_is_a_real_flow(self, tmp_path) -> None:
        source = workspace(tmp_path).read("nmos.in")

        assert "structure out=1_substrate.str" in source
        assert "structure out=25_metal_contact.str" in source

    def test_existing_workspace_is_left_alone(self, tmp_path) -> None:
        """이미 쓰던 사람의 작업공간에 예제를 밀어 넣지 않는다."""
        root = tmp_path / "user-1"
        root.mkdir(parents=True)
        (root / "mine.in").write_text("init boron conc=1e15\n")

        assert [entry.name for entry in workspace(tmp_path).list()] == ["mine.in"]

    def test_deleting_the_example_makes_it_stay_deleted(self, tmp_path) -> None:
        """지운 파일이 되살아나면 지울 방법이 없다."""
        space = workspace(tmp_path)
        space.delete("nmos.in")

        assert space.list() == []

    def test_seeding_twice_is_harmless(self, tmp_path) -> None:
        # 같은 순간에 두 요청이 들어오면 둘 다 씨앗을 뿌리려 할 수 있다.
        root = tmp_path / "user-1"
        root.mkdir(parents=True)
        seed(root)
        seed(root)

        assert [p.name for p in root.iterdir()] == ["nmos.in"]

    def test_counts_toward_usage(self, tmp_path) -> None:
        """예제도 사용자 파일이다. 셈에서 빼면 용량 표시가 어긋난다."""
        assert workspace(tmp_path).usage().used_bytes > 0


class TestBundledCopy:
    def test_matches_the_repo_example(self) -> None:
        """패키지 안 사본과 레포 예제가 갈라지면 안 된다.

        런타임은 패키지 사본만 읽는다(레포 트리가 없는 설치에서도 돌아야
        한다). 그래서 원본을 고쳤을 때 사본이 그대로 남는 것을 여기서 잡는다.
        """
        original = REPO_ROOT / "SUPREM4GS" / "examples" / "mosfet" / "nmos.in"
        if not original.exists():
            import pytest

            pytest.skip("레포 예제를 찾을 수 없습니다")

        packaged = EXAMPLES / "nmos.in"

        assert packaged.read_bytes() == original.read_bytes()
