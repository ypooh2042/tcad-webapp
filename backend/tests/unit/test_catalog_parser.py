"""suprem.key 파싱과 런타임 이름 규칙.

메타데이터(설명·단위·기본값·오류 조건)는 suprem.key 에만 있다. 그런데 실행
시점에 시뮬레이터가 읽는 파일은 suprem.uk 이고, 거기서는 이름이 11자로 잘려
있다. 카탈로그는 **런타임이 받아들이는 이름**을 내놓아야 한다. 그러지 않으면
자동완성이 실행되지 않는 코드를 만들어 준다.

실제 시뮬레이터로 확인한 경계:
    deposit ... concentration=1e18   (13자) → errors detected
    deposit ... concentratio=1e18    (12자) → errors detected
    deposit ... concentrati=1e18     (11자) → 정상
    deposit ... concent=1e18         (7자)  → 정상
"""

from __future__ import annotations

import pytest

from app.catalog.models import RUNTIME_NAME_LIMIT, ParameterType
from app.catalog.key_parser import parse_key

SNIPPET = """
#card 0
#initialize the mesh
card initialize;
{
    string infile units = "structure file for read";

    float conc  units = "background concentration"
    message = "concentrations must be positive"
    error = (conc < 0.0);

    #identifiers for the different impurities
    switch impurity = 1 units = "background doping type"
    message = "Only one impurity";
    {
	boolean arsenic;
	boolean boron;
    }
}

#card 1
card deposit;
{
    float concentration units = "dopant concentration";
    boolean oxide;	#deposit oxide
}
"""


@pytest.fixture(scope="module")
def commands():
    return parse_key(SNIPPET)


@pytest.fixture(scope="module")
def by_name(commands):
    return {command.name: command for command in commands}


class TestStructure:
    def test_finds_every_card(self, commands) -> None:
        assert [command.name for command in commands] == ["initialize", "deposit"]

    def test_card_description_comes_from_preceding_comments(self, by_name) -> None:
        assert by_name["initialize"].description == "initialize the mesh"

    def test_trailing_comment_becomes_description(self, by_name) -> None:
        oxide = by_name["deposit"].parameter("oxide")

        assert oxide.description == "deposit oxide"


class TestParameters:
    def test_reads_units(self, by_name) -> None:
        assert by_name["initialize"].parameter("infile").units == (
            "structure file for read"
        )

    def test_reads_error_condition_and_message(self, by_name) -> None:
        conc = by_name["initialize"].parameter("conc")

        assert conc.error == "( conc < 0.0 )"
        assert conc.message == "concentrations must be positive"

    @pytest.mark.parametrize(
        ("param", "expected"),
        [
            ("infile", ParameterType.STRING),
            ("conc", ParameterType.FLOAT),
            ("arsenic", ParameterType.BOOLEAN),
        ],
    )
    def test_reads_types(self, by_name, param, expected) -> None:
        assert by_name["initialize"].parameter(param).type is expected


class TestSwitchGroups:
    """switch 는 상호배타 선택지 묶음이다. 묶음을 잃으면 사용자에게 "둘 중
    하나만" 이라고 알려줄 수 없다."""

    def test_members_are_flattened_into_parameters(self, by_name) -> None:
        names = [p.name for p in by_name["initialize"].parameters]

        assert "arsenic" in names and "boron" in names

    def test_members_keep_their_group(self, by_name) -> None:
        arsenic = by_name["initialize"].parameter("arsenic")

        assert arsenic.group == "impurity"
        assert arsenic.group_message == "Only one impurity"

    def test_ordinary_parameters_have_no_group(self, by_name) -> None:
        assert by_name["initialize"].parameter("conc").group is None


class TestRuntimeNameTruncation:
    """11자를 넘는 이름은 런타임에 잘린 형태로만 존재한다."""

    def test_long_name_is_truncated(self, by_name) -> None:
        assert by_name["deposit"].parameter("concentrati").name == "concentrati"

    def test_original_name_is_kept_for_documentation(self, by_name) -> None:
        param = by_name["deposit"].parameter("concentrati")

        assert param.source_name == "concentration"
        assert param.truncated is True

    def test_full_name_is_not_offered(self, by_name) -> None:
        """카탈로그가 원형을 내놓으면 자동완성이 실행 안 되는 코드를 만든다."""
        names = [p.name for p in by_name["deposit"].parameters]

        assert "concentration" not in names

    def test_short_names_are_untouched(self, by_name) -> None:
        param = by_name["initialize"].parameter("conc")

        assert param.truncated is False
        assert param.source_name == "conc"

    def test_limit_matches_the_measured_boundary(self) -> None:
        assert RUNTIME_NAME_LIMIT == 11


@pytest.fixture(scope="module")
def catalog():
    from app.catalog.catalog import load_catalog

    return load_catalog()


class TestRealKeyFile:
    """레포에 들어 있는 실제 suprem.key 로 확인한다."""

    def test_parses_all_cards(self, catalog) -> None:
        assert len(catalog.commands) == 45

    def test_parses_all_parameters(self, catalog) -> None:
        total = sum(len(c.parameters) for c in catalog.commands)

        assert total == 1175

    def test_no_name_exceeds_the_runtime_limit(self, catalog) -> None:
        too_long = [
            p.name
            for command in catalog.commands
            for p in command.parameters
            if len(p.name) > RUNTIME_NAME_LIMIT
        ] + [c.name for c in catalog.commands if len(c.name) > RUNTIME_NAME_LIMIT]

        assert too_long == []

    def test_truncation_creates_no_duplicate_names(self, catalog) -> None:
        """자르고 나서 두 파라미터 이름이 같아지면 둘 다 못 쓰게 된다."""
        for command in catalog.commands:
            names = [p.name for p in command.parameters]
            assert len(names) == len(set(names)), command.name

    def test_marks_unreachable_parameters(self, catalog) -> None:
        """다른 이름의 진접두사인 이름은 어떤 입력으로도 지목할 수 없다.

        실제 시뮬레이터에서 structure backside 가 "ambiguous parameter" 로
        거절되는 것을 확인했다. 카탈로그가 이걸 표시하지 않으면 사용자는
        문서에 있는 파라미터가 왜 안 되는지 알 수 없다.
        """
        structure = catalog.get("structure")
        backside = structure.parameter("backside")

        assert backside.unreachable is True
        assert structure.parameter("backside.y").unreachable is False

    def test_only_backside_is_unreachable(self, catalog) -> None:
        unreachable = [
            (command.name, p.name)
            for command in catalog.commands
            for p in command.parameters
            if p.unreachable
        ]

        assert unreachable == [("structure", "backside")]

    def test_known_command_metadata(self, catalog) -> None:
        initialize = catalog.get("initialize")

        assert initialize.parameter("conc").units == "background concentration"
        assert initialize.parameter("boron").group == "impurity"
