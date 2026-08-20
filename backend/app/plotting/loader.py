"""파싱한 구조를 캐시한다.

CMOS 예제 하나가 450KB 고, 화면은 물리량을 바꾸거나 컷 라인을 끌 때마다 같은
파일을 다시 요청한다. 매번 파싱하면 컷 라인을 끄는 동안 서버가 계속 그 파일을
다시 읽는다.

캐시 키에 mtime 과 크기를 넣는다. 경로만 쓰면 같은 잡을 다시 돌려 파일이 바뀌어도
옛 내용을 계속 보여준다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.str_parser.models import Structure
from app.str_parser.parser import parse_structure

#: 접속한 사람들이 각자 몇 단계씩 훑어볼 수 있는 정도. 하나가 수 MB 이므로
#: 무한정 늘리면 워커 메모리를 잠식한다.
_CACHE_SIZE = 32


@lru_cache(maxsize=_CACHE_SIZE)
def _parse_cached(path: str, mtime_ns: int, size: int) -> Structure:
    # mtime_ns 와 size 는 캐시 키로만 쓴다. 값 자체는 필요 없다.
    del mtime_ns, size
    return parse_structure(Path(path).read_text(errors="replace"))


def load_structure(path: Path) -> Structure:
    """`.str` 파일을 파싱한다. 내용이 그대로면 다시 파싱하지 않는다."""
    stat = path.stat()
    return _parse_cached(str(path), stat.st_mtime_ns, stat.st_size)


def clear_cache() -> None:
    """테스트에서 캐시 영향을 끊을 때 쓴다."""
    _parse_cached.cache_clear()
