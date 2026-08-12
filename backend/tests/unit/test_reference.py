"""커맨드 레퍼런스.

매뉴얼 산문과 suprem.key 문법을 미리 합쳐 둔 목록이다. 검색과 달리 **무엇을
찾아야 할지 모를 때** 쓰는 것이라, 전부 다 담고 있는지가 중요하다 — 빠진
커맨드는 사용자에게 존재하지 않는 것과 같다.
"""

from __future__ import annotations

import pytest

from app.catalog.catalog import load_catalog
from app.docs.reference import load_reference


@pytest.fixture(scope="module")
def reference():
    return load_reference()


class TestCoverage:
    def test_covers_every_manual_command(self, reference):
        # 매뉴얼이 설명하는 커맨드는 50개다.
        documented = [c for c in reference.commands if c.documented]

        assert len(documented) == 50

    def test_covers_every_catalog_command(self, reference):
        """suprem.key 에 있는 커맨드가 하나도 빠지면 안 된다.

        매뉴얼에 설명이 없다고 빼면 사용자는 그런 커맨드가 있다는 사실조차
        모른다 — 문법은 알려줄 수 있으므로 표시만 하고 싣는다.

        런타임 이름(`interstitia`)과 매뉴얼 이름(`interstitial`) 어느 쪽으로도
        찾을 수 있어야 한다. 레퍼런스는 사람이 읽는 것이라 매뉴얼 이름을 싣지만,
        그것만 보고 카탈로그 커맨드가 빠졌다고 착각하면 안 된다.
        """
        listed = {c.name for c in reference.commands}
        listed |= {c.runtime_name for c in reference.commands}

        for command in load_catalog().commands:
            assert command.name in listed, f"{command.name} 이 레퍼런스에 없다"

    def test_records_the_runtime_name(self, reference):
        """런타임은 커맨드 이름을 11자로 자른다 — 하지만 **입력도 11자로 잘라**
        비교하므로 전체 이름을 쳐도 통과한다(실측 확인).

        파라미터와 다르다. 파라미터 `concentration` 은 전체 이름을 치면
        "parameter concentration does not exist" 로 거절당한다. 그래서 잘림
        경고는 파라미터에만 붙인다.
        """
        interstitial = reference.get("interstitial")

        assert interstitial.name == "interstitial"
        assert interstitial.runtime_name == "interstitia"

    def test_short_command_names_are_unchanged(self, reference):
        assert reference.get("implant").runtime_name == "implant"

    def test_every_command_belongs_to_a_group(self, reference):
        grouped = {name for group in reference.groups for name in group.commands}

        assert {c.name for c in reference.commands} == grouped

    def test_no_command_appears_twice(self, reference):
        names = [name for group in reference.groups for name in group.commands]

        assert len(names) == len(set(names))


class TestGrouping:
    def test_uses_the_manual_own_classification(self, reference):
        """분류는 매뉴얼 p.51 이 나눈 것을 그대로 쓴다.

        임의로 다시 묶으면 매뉴얼과 대조할 수 없다.
        """
        by_name = {group.name: group for group in reference.groups}

        assert "implant" in by_name["공정 시뮬레이션"].commands
        assert "structure" in by_name["데이터 입출력"].commands
        assert "plot.1d" in by_name["결과 보기"].commands

    def test_shell_builtins_are_separate(self, reference):
        # 셸 내장은 suprem.key 에 없다. 파라미터 표가 비는 것이 정상이다.
        by_name = {group.name: group for group in reference.groups}

        assert "for" in by_name["셸 내장"].commands

    def test_every_group_explains_itself(self, reference):
        for group in reference.groups:
            assert group.note, f"{group.name} 에 설명이 없다"


class TestEntries:
    def test_carries_the_manual_summary(self, reference):
        implant = reference.get("implant")

        assert implant.summary == "Perform ion implantation."

    def test_carries_the_catalog_parameters(self, reference):
        implant = reference.get("implant")
        names = {p.name for p in implant.parameters}

        assert {"dose", "energy"} <= names

    def test_matches_truncated_names_to_manual_names(self, reference):
        """매뉴얼은 `interstitial`, 카탈로그는 11자로 자른 `interstitia` 다.

        한쪽 이름만 키로 쓰면 이 커맨드의 파라미터가 통째로 빈다.
        """
        interstitial = reference.get("interstitial")

        assert len(interstitial.parameters) > 0

    def test_keeps_the_page_number(self, reference):
        # 원본을 같이 보려면 쪽 번호가 있어야 한다.
        assert reference.get("implant").manual_page == "67"

    def test_marks_undocumented_commands(self, reference):
        # suprem.key 에는 있는데 매뉴얼에 설명이 없다.
        device = reference.get("device")

        assert device.documented is False
        assert device.parameters

    def test_links_to_the_manual_section(self, reference):
        # 목록에서 고르면 이 id 로 본문을 읽는다.
        assert reference.get("implant").manual_section_id

    def test_undocumented_commands_have_no_section(self, reference):
        assert reference.get("device").manual_section_id is None


class TestLookup:
    def test_unknown_name_raises(self, reference):
        with pytest.raises(KeyError):
            reference.get("nonexistent")

    def test_parsed_once_per_process(self):
        # 800KB 다. 요청마다 파싱하면 목록 여는 것만으로 느려진다.
        assert load_reference() is load_reference()
