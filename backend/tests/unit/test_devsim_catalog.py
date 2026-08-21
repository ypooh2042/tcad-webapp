"""전극이 있는 구조를 오래 보관하기.

잡 산출물은 유휴·쿼터 스윕에 지워진다. 공정을 돌린 다음 날 소자 해석을 하려면
그때마다 공정을 다시 돌려야 한다는 뜻이라, 전극이 있는 것만 골라 따로 둔다.

같은 `.in` 을 다시 돌리면 그 `.in` 에서 나온 것은 전부 지우고 새로 채운다.
공정 코드를 고쳐 다시 돌렸는데 옛 구조가 목록에 남아 있으면, 어느 것이 지금
코드의 결과인지 구분할 수 없다.
"""

from pathlib import Path

import pytest

from app.devsim.catalog import place_files, slug_of

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestSlug:
    def test_keeps_it_readable(self) -> None:
        # 사람이 보관소를 열어 봤을 때 어느 코드에서 나온 것인지 알아야 한다.
        assert slug_of("mosfet/nmos.in").startswith("mosfet-nmos.in-")

    def test_paths_that_clean_to_the_same_text_stay_apart(self) -> None:
        # 읽기 좋은 부분만 남기면 이 둘이 같은 이름이 된다.
        assert slug_of("mosfet/nmos.in") != slug_of("mosfet-nmos.in")

    def test_strips_path_tricks(self) -> None:
        # 경로가 보관소 밖으로 나가면 안 된다.
        assert "/" not in slug_of("../../etc/passwd")
        assert ".." not in slug_of("../../etc/passwd")

    def test_never_empty(self) -> None:
        assert slug_of("") != ""
        assert slug_of("///") != ""

    def test_different_paths_stay_different(self) -> None:
        assert slug_of("a/x.in") != slug_of("b/x.in")


class TestPlaceFiles:
    def _artifacts(self, tmp_path) -> list[tuple[int, Path]]:
        good = tmp_path / "job" / "with_metal.str"
        bare = tmp_path / "job" / "no_metal.str"
        good.parent.mkdir(parents=True, exist_ok=True)
        good.write_text((FIXTURES / "2d_contacts.str").read_text())
        bare.write_text((FIXTURES / "2d_cmos_source.str").read_text())
        return [(1, bare), (2, good)]

    def test_keeps_only_the_ones_with_electrodes(self, tmp_path) -> None:
        placed = place_files(
            tmp_path / "store", owner_id=1, source_path="a.in",
            artifacts=self._artifacts(tmp_path),
        )
        assert [entry.filename for entry in placed] == ["with_metal.str"]

    def test_copies_out_of_the_job_directory(self, tmp_path) -> None:
        placed = place_files(
            tmp_path / "store", owner_id=1, source_path="a.in",
            artifacts=self._artifacts(tmp_path),
        )
        kept = Path(placed[0].path)
        assert kept.exists()
        assert (tmp_path / "store") in kept.parents
        # 잡 디렉토리를 지워도 살아 있어야 한다.
        assert kept.read_text() == (FIXTURES / "2d_contacts.str").read_text()

    def test_remembers_where_it_came_from(self, tmp_path) -> None:
        placed = place_files(
            tmp_path / "store", owner_id=1, source_path="a.in",
            artifacts=self._artifacts(tmp_path),
        )
        assert placed[0].sequence == 2

    def test_a_rerun_replaces_the_old_files(self, tmp_path) -> None:
        store = tmp_path / "store"
        place_files(
            store, owner_id=1, source_path="a.in",
            artifacts=self._artifacts(tmp_path),
        )
        # 두 번째 실행에서는 전극이 있는 구조가 없다고 하자.
        placed = place_files(store, owner_id=1, source_path="a.in", artifacts=[])
        assert placed == []
        # 옛 파일이 남아 있으면 어느 것이 지금 코드의 결과인지 알 수 없다.
        left = list((store / "user-1").rglob("*.str"))
        assert left == []

    def test_other_sources_are_untouched(self, tmp_path) -> None:
        store = tmp_path / "store"
        place_files(
            store, owner_id=1, source_path="a.in",
            artifacts=self._artifacts(tmp_path),
        )
        place_files(
            store, owner_id=1, source_path="b.in",
            artifacts=self._artifacts(tmp_path),
        )
        place_files(store, owner_id=1, source_path="a.in", artifacts=[])
        left = sorted(p.name for p in (store / "user-1").rglob("*.str"))
        assert left == ["with_metal.str"]

    def test_other_users_are_untouched(self, tmp_path) -> None:
        store = tmp_path / "store"
        place_files(
            store, owner_id=1, source_path="a.in",
            artifacts=self._artifacts(tmp_path),
        )
        place_files(
            store, owner_id=2, source_path="a.in",
            artifacts=self._artifacts(tmp_path),
        )
        place_files(store, owner_id=1, source_path="a.in", artifacts=[])
        assert list((store / "user-2").rglob("*.str"))
        assert not list((store / "user-1").rglob("*.str"))
