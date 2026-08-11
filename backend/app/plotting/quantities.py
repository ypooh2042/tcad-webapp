"""플롯할 수 있는 물리량.

`.str` 에 저장된 컬럼을 그대로 쓰되, net_doping 만은 예외다.
"""

from __future__ import annotations

from app.str_parser.models import NodeSolution, Structure

#: 활성 도너 − 활성 억셉터. 파일에도 같은 이름의 컬럼(코드 24)이 있지만 쓰지
#: 않는다. 전기 시뮬레이션을 돌리지 않은 순수 공정 결과에서는 실제 도핑이
#: 있어도 0 으로 기록되는 것을 CMOS 예제에서 확인했다. 저장값을 그대로
#: 보여주면 도핑이 없는 소자처럼 보인다.
NET_DOPING = "net_doping"


def value_of(solution: NodeSolution, quantity: str) -> float:
    """한 노드에서 물리량 값을 읽는다.

    net_doping 은 저장값 대신 활성 농도로 계산한다. 이 판정이 저장 컬럼 조회보다
    **먼저** 와야 한다. 그렇지 않으면 CMOS 처럼 코드 24 를 가진 파일에서
    쓸모없는 0 이 나온다.
    """
    if quantity == NET_DOPING:
        return solution.net_doping()
    return solution.value(quantity)


def available(structure: Structure) -> tuple[str, ...]:
    """이 구조에서 그릴 수 있는 물리량 이름."""
    names = [
        species.name
        for species in structure.species
        if species.name != NET_DOPING
    ]
    # 도펀트가 하나라도 있으면 net_doping 을 계산할 수 있다.
    if structure.table.donor_positions or structure.table.acceptor_positions:
        names.append(NET_DOPING)
    return tuple(names)
