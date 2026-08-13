"""플롯할 수 있는 물리량.

`.str` 에 저장된 컬럼을 그대로 쓰되, net_doping 만은 예외다.
"""

from __future__ import annotations

from app.str_parser.models import NodeSolution, Structure

#: 활성 도너 − 활성 억셉터. **파일에는 net doping 컬럼이 없다.**
#: 한동안 코드 24 를 net_doping 으로 읽었지만, 상류 impurity.h 는 그것을
#: `GRN`(폴리실리콘 결정립 크기)로 정의한다. 값이 늘 0 이라 도핑으로 쓰면
#: 도핑이 없는 소자처럼 보였다.
NET_DOPING = "net_doping"


def value_of(solution: NodeSolution, quantity: str) -> float:
    """한 노드에서 물리량 값을 읽는다.

    net_doping 은 계산으로만 존재한다. 저장 컬럼에는 없는 이름이므로 이 분기가
    없으면 조회에 실패한다.
    """
    if quantity == NET_DOPING:
        return solution.net_doping()
    return solution.value(quantity)


def available(structure: Structure) -> tuple[str, ...]:
    """이 구조에서 그릴 수 있는 물리량 이름."""
    names = [species.name for species in structure.species]
    # 도펀트가 하나라도 있으면 net_doping 을 계산할 수 있다.
    if structure.table.donor_positions or structure.table.acceptor_positions:
        names.append(NET_DOPING)
    return tuple(names)
