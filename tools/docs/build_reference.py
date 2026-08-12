#!/usr/bin/env python3
"""SUPREM-IV.GS 커맨드 레퍼런스를 만든다.

두 출처를 하나로 합친다:

    매뉴얼(320쪽 PDF)  → 무엇을 하는 커맨드인가, 어떻게 쓰는가, 예제
    suprem.key         → 받는 파라미터, 타입, 기본값, 제약

둘 중 하나만으로는 부족하다. 매뉴얼만 보면 이름이 11자로 잘린다는 사실을 모르고,
suprem.key 만 보면 `dose` 가 float 이라는 것만 알고 무슨 뜻인지 모른다.

**분류는 매뉴얼이 정한 것을 그대로 쓴다.** 매뉴얼의 "Commands" 장이 커맨드를
네 무리로 나눠 설명하고 있어서, 임의로 다시 묶으면 매뉴얼과 대조하기 어려워진다.

    python tools/docs/build_reference.py

출력:
    backend/app/docs/data/reference.json   앱이 읽는 구조화 데이터
    SUPREM4GS/COMMAND_REFERENCE.md         사람이 읽는 목록
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANUAL = REPO_ROOT / "backend" / "app" / "docs" / "data" / "manual.json"
JSON_OUT = REPO_ROOT / "backend" / "app" / "docs" / "data" / "reference.json"
MARKDOWN_OUT = REPO_ROOT / "SUPREM4GS" / "COMMAND_REFERENCE.md"

sys.path.insert(0, str(REPO_ROOT / "backend"))

#: 매뉴얼 "Commands" 장(p.51)이 직접 나눈 무리. 순서도 매뉴얼을 따른다 —
#: 데이터를 넣고, 공정을 돌리고, 결과를 보고, 나머지.
COMMAND_GROUPS: dict[str, tuple[str, ...]] = {
    "데이터 입출력": (
        "mode",
        "line",
        "region",
        "boundary",
        "initialize",
        "profile",
        "structure",
    ),
    "공정 시뮬레이션": ("deposit", "etch", "implant", "diffuse", "stress", "method"),
    "결과 보기": (
        "select",
        "plot.1d",
        "plot.2d",
        "contour",
        "print.1d",
        "label",
        "option",
    ),
    "기타": ("cpulog", "echo", "printf", "pause"),
    "셸 내장": ("define", "undef", "set", "unset", "for", "source", "help", "man"),
}

#: 물성 계수 커맨드. 매뉴얼의 "Models" 장(p.127)에 해당한다. 도펀트별로 하나씩
#: 있고 내용 구조가 같아서, 이름만 나열하는 편이 읽기 쉽다.
MODEL_GROUP = "물성 계수"
UNDOCUMENTED_GROUP = "문서 없음"

GROUP_NOTES = {
    "데이터 입출력": "격자와 재질을 정의하고, 구조를 파일로 주고받는다.",
    "공정 시뮬레이션": "실제 공정 단계. 이 커맨드들이 웨이퍼를 바꾼다.",
    "결과 보기": "계산이 끝난 구조에서 값을 꺼내 그리거나 출력한다.",
    "기타": "출력·계산·대기 같은 보조 기능.",
    "셸 내장": "인터프리터가 직접 처리한다. suprem.key 에 정의되어 있지 않다.",
    MODEL_GROUP: (
        "확산·편석·클러스터링 계수를 바꾼다. 기본값은 data/modelrc 에 있고 "
        "사람이 읽을 수 있는 형식이다."
    ),
    UNDOCUMENTED_GROUP: (
        "suprem.key 에는 있지만 매뉴얼에 설명이 없다. 받는 파라미터는 알 수 "
        "있어도 무엇을 하는 커맨드인지는 직접 확인해야 한다."
    ),
}


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def first_sentence(text: str) -> str:
    body = collapse(text)
    match = re.match(r"(.{20,200}?\.)(\s|$)", body)
    return match.group(1) if match else body[:200]


def load_manual() -> dict[str, dict]:
    raw = json.loads(MANUAL.read_text())
    by_command: dict[str, dict] = {}
    for section in raw["sections"]:
        if section["kind"] == "command" and section["command"]:
            by_command[section["command"]] = section
    return by_command


def load_catalog() -> dict[str, object]:
    """suprem.key 카드를 이름으로 찾을 수 있게 담는다.

    **11자로 잘린 이름과 원형을 둘 다 키로 넣는다.** 카탈로그는 런타임이
    인식하는 이름(`interstitia`)을 쓰고 매뉴얼은 원형(`interstitial`)을 쓴다.
    한쪽만 키로 두면 그 커맨드의 파라미터가 통째로 비어 버린다 — 실제로
    처음에 그렇게 만들었다.
    """
    from app.catalog.catalog import load_catalog as load

    by_name: dict[str, object] = {}
    for command in load().commands:
        by_name[command.name] = command
        by_name[command.source_name] = command
    return by_name


def build_entry(name: str, group: str, manual: dict, catalog: dict) -> dict:
    section = manual.get(name)
    command = catalog.get(name)

    subsections = section["subsections"] if section else {}
    summary = collapse(subsections.get("SUMMARY", ""))
    if not summary:
        summary = first_sentence(subsections.get("DESCRIPTION", ""))

    return {
        "name": name,
        # 런타임이 인식하는 이름. 11자를 넘으면 잘린다. 다만 입력도 같이 잘려
        # 비교되므로 전체 이름을 쳐도 통과한다(실측). 파라미터와 다른 점이다.
        "runtime_name": getattr(command, "name", name),
        "group": group,
        "summary": summary,
        "documented": bool(section),
        "synopsis": (subsections.get("SYNOPSIS") or "").strip(),
        "description": (subsections.get("DESCRIPTION") or "").strip(),
        "examples": (subsections.get("EXAMPLES") or "").strip(),
        "see_also": collapse(subsections.get("SEE ALSO", "")),
        "manual_page": section["page_start"] if section else None,
        "manual_section_id": section["id"] if section else None,
        "parameters": [
            {
                "name": parameter.name,
                "type": parameter.type.value,
                "default": parameter.default,
                "units": parameter.units,
                "error": parameter.error,
                "message": parameter.message,
                "group": parameter.group,
                "source_name": parameter.source_name,
                "truncated": parameter.truncated,
                "unreachable": parameter.unreachable,
            }
            for parameter in (command.parameters if command else ())
        ],
    }


def main() -> None:
    manual = load_manual()
    catalog = load_catalog()

    grouped = dict(COMMAND_GROUPS)
    # 나머지 매뉴얼 커맨드는 전부 물성 계수다. 목록을 손으로 적으면 도펀트가
    # 추가될 때 조용히 빠진다.
    listed = {name for names in grouped.values() for name in names}
    grouped[MODEL_GROUP] = tuple(sorted(set(manual) - listed))

    entries = [
        build_entry(name, group, manual, catalog)
        for group, names in grouped.items()
        for name in names
    ]

    # suprem.key 에는 있는데 매뉴얼에 문서가 없는 커맨드. 목록에서 빼면
    # 사용자는 그런 커맨드가 있다는 사실조차 모른다 — 문법은 카탈로그가
    # 알고 있으므로 문서 없음만 표시해 함께 싣는다.
    documented = {name for names in grouped.values() for name in names}
    documented |= {entry.get("source_name", "") for entry in entries}
    undocumented = sorted(
        name
        for name, command in catalog.items()
        if name == getattr(command, "name", None) and name not in documented
        and getattr(command, "source_name", name) not in documented
    )
    if undocumented:
        grouped[UNDOCUMENTED_GROUP] = tuple(undocumented)
        entries += [
            build_entry(name, UNDOCUMENTED_GROUP, manual, catalog)
            for name in undocumented
        ]

    payload = {
        "groups": [
            {
                "name": group,
                "note": GROUP_NOTES.get(group, ""),
                "commands": list(names),
            }
            for group, names in grouped.items()
        ],
        "commands": entries,
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    MARKDOWN_OUT.write_text(render_markdown(payload))

    total_parameters = sum(len(e["parameters"]) for e in entries)
    documented = sum(1 for e in entries if e["description"])
    print(f"커맨드      : {len(entries)}")
    print(f"  설명 있음 : {documented}")
    print(f"  파라미터  : {total_parameters}")
    for group in payload["groups"]:
        print(f"  {group['name']:<12} {len(group['commands'])}")
    print(f"-> {JSON_OUT.relative_to(REPO_ROOT)}")
    print(f"-> {MARKDOWN_OUT.relative_to(REPO_ROOT)}")


def render_markdown(payload: dict) -> str:
    by_name = {entry["name"]: entry for entry in payload["commands"]}
    lines = [
        "# SUPREM-IV.GS 커맨드 레퍼런스",
        "",
        "매뉴얼(320쪽 PDF)과 `data/suprem.key` 를 합쳐 만든 목록이다.",
        "`tools/docs/build_reference.py` 가 생성하므로 직접 고치지 말 것.",
        "",
        "분류는 매뉴얼의 \"Commands\" 장(p.51)이 나눈 것을 그대로 따랐다.",
        "",
        "## 목차",
        "",
    ]

    for group in payload["groups"]:
        lines.append(f"- **{group['name']}** — {group['note']}")
        for name in group["commands"]:
            entry = by_name[name]
            lines.append(f"  - [`{name}`](#{name.replace('.', '')}) {entry['summary']}")
    lines.append("")

    for group in payload["groups"]:
        lines += [f"## {group['name']}", "", group["note"], ""]
        for name in group["commands"]:
            entry = by_name[name]
            lines += [f"### {name}", ""]
            if entry["summary"]:
                lines += [entry["summary"], ""]
            if entry["manual_page"]:
                lines += [f"매뉴얼 {entry['manual_page']}쪽", ""]
            if entry["synopsis"]:
                lines += ["```", entry["synopsis"], "```", ""]
            if entry["parameters"]:
                lines += _parameter_table(entry["parameters"])
    return "\n".join(lines) + "\n"


def _parameter_table(parameters: list[dict]) -> list[str]:
    rows = ["| 파라미터 | 타입 | 기본값 | 설명 |", "|---|---|---|---|"]
    for parameter in parameters:
        name = f"`{parameter['name']}`"
        if parameter["truncated"]:
            # 문서에 적힌 이름과 실제로 써야 하는 이름이 다르다. 말해 주지
            # 않으면 사용자가 오타로 오해한다.
            name += f" (문서상 `{parameter['source_name']}`)"
        if parameter["unreachable"]:
            name += " ⚠사용 불가"
        note = parameter["units"] or ""
        if parameter["group"]:
            note += f" · `{parameter['group']}` 중 택1"
        rows.append(
            f"| {name} | {parameter['type']} | "
            f"{parameter['default'] or '—'} | {note.strip()} |"
        )
    return [*rows, ""]


if __name__ == "__main__":
    main()
