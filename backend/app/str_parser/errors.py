"""`.str` 파싱 예외."""


class StructureFormatError(ValueError):
    """`.str` 파일이 기대한 포맷 불변식을 위반했을 때.

    조용히 잘못된 값을 반환하는 것보다 즉시 실패하는 편이 안전하다. 컬럼 개수가
    어긋난 채로 통과하면 도핑 프로파일이 엉뚱한 quantity 로 그려지기 때문이다.
    """
