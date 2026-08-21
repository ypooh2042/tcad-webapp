"""새 사용자에게 소자 해석용 구조를 하나 쥐어 준다.

작업공간에는 `nmos.in` 이 들어간다(`app/workspace/starter.py`). 그런데 소자
해석은 **실행 결과**(`.str`)를 입력으로 받으므로, 예제를 한 번 돌리기 전에는
소자 해석 탭이 비어 있다. 처음 들어온 사람이 그 탭에서 아무것도 못 보는 것을
막으려면 구조도 함께 넣어야 한다.

`.in` 과 같은 이름표(`nmos.in`)를 달아 둔다. 사용자가 자기 `nmos.in` 을 돌리면
그 결과가 이 자리를 대신한다 — 같은 `.in` 에서 나온 것은 갈아 끼우는 규칙이
그대로 적용된다.
"""

from pathlib import Path

from app.devsim.screening import analysable
from app.workspace.starter import STARTER_SOURCE, STARTER_STRUCTURE, seed_structure

EXAMPLES = Path(__file__).parent.parent.parent / "app" / "workspace" / "examples"


class TestBundledStructure:
    def test_the_example_structure_ships_with_the_package(self) -> None:
        assert (EXAMPLES / STARTER_STRUCTURE).exists()

    def test_it_has_electrodes(self) -> None:
        # 전극이 없으면 목록에 올라가지도 않는다. 넣는 의미가 없다.
        assert analysable(EXAMPLES / STARTER_STRUCTURE) is True

    def test_it_is_labelled_with_the_deck_that_made_it(self) -> None:
        # 사용자가 자기 nmos.in 을 돌리면 이 자리를 대신해야 한다.
        assert STARTER_SOURCE == "nmos.in"


class TestSeedStructure:
    def test_copies_it_into_the_store(self, tmp_path) -> None:
        placed = seed_structure(tmp_path, owner_id=3)
        assert placed is not None
        kept = Path(placed.path)
        assert kept.exists()
        assert kept.name == STARTER_STRUCTURE

    def test_reports_what_the_catalog_needs(self, tmp_path) -> None:
        placed = seed_structure(tmp_path, owner_id=3)
        assert placed.filename == STARTER_STRUCTURE
        assert placed.size_bytes > 0
        assert placed.sequence >= 1

    def test_each_user_gets_their_own_copy(self, tmp_path) -> None:
        one = seed_structure(tmp_path, owner_id=1)
        two = seed_structure(tmp_path, owner_id=2)
        assert one.path != two.path
        assert Path(one.path).exists() and Path(two.path).exists()

    def test_running_the_deck_replaces_it(self, tmp_path) -> None:
        # 같은 `.in` 에서 나온 것은 갈아 끼운다는 규칙이 그대로 적용돼야 한다.
        from app.devsim.catalog import place_files

        seed_structure(tmp_path, owner_id=1)
        place_files(tmp_path, owner_id=1, source_path=STARTER_SOURCE, artifacts=[])
        assert list((tmp_path / "user-1").rglob("*.str")) == []
