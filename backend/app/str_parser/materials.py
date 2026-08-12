"""`.str` 파일의 material_id → 물질 이름 매핑.

CMOS.in 의 공정 단계별 `.str` 을 순서대로 대조해 확정했다. 각 단계에서 물질이
하나씩 추가될 때 새 id 가 정확히 그 시점에 나타난다:

    substrate.str       r 1 3                    → 3 = silicon
    oxidation.str       r 1 3, r 2 1             → 1 = oxide
    nitride.str         r 1 3, r 2 1, r 3 2      → 2 = nitride
    nitride_remove.str  r 1 3, r 2 1             → nitride 제거 후 region 소멸(일관성 확인)
    poly_gate.str       r 1 3, r 2 1, r 3 4      → 4 = poly

id 0 은 `r` 라인에 나타나지 않고 `n` 라인에만 등장한다. 노출 표면 바깥의 ambient
(가스)를 가리킨다.

주의: 이 번호 체계는 `data/sup4gs.imp` 헤더의 material id 와 **다르다**.
sup4gs.imp 는 implant 통계 파일 전용 번호(oxide=5 등)를 쓴다. 혼동 금지.
"""

from __future__ import annotations

AMBIENT_MATERIAL_ID = 0

_MATERIAL_NAMES: dict[int, str] = {
    AMBIENT_MATERIAL_ID: "ambient",
    1: "oxide",
    2: "nitride",
    3: "silicon",
    4: "poly",
    # 5~8 은 물질을 하나씩만 증착해 확인했다. silicon(3) 위에 region 이 하나
    # 생기고 그 id 가 곧 그 물질의 번호다. 금속배선 구조가 통째로 "모르는 재질"
    # 로 보이던 것이 이 빈칸 때문이었다.
    5: "oxynitride",
    6: "aluminum",
    7: "photoresist",
    8: "gaas",
}


def resolve_material(material_id: int) -> str:
    """material_id 를 이름으로 바꾼다.

    미확인 id(gaas 계열 예제 등에서 나올 수 있음)는 `unknown_<id>` 로 보존한다.
    조용히 다른 물질로 잘못 표시하는 것보다 모른다고 드러내는 편이 안전하다.
    """
    return _MATERIAL_NAMES.get(material_id, f"unknown_{material_id}")


def is_known_material(material_id: int) -> bool:
    return material_id in _MATERIAL_NAMES
