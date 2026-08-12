"""사용자 작업공간의 경로 해석.

**이 모듈이 뚫리면 서버 파일시스템 전체가 열린다.** 사용자가 보내는 경로는
전부 신뢰할 수 없는 입력이다. `..`, 절대경로, 널 바이트는 문자열 단계에서
걸러내고, 심볼릭 링크는 문자열 검사를 그냥 통과하므로 **실제로 따라가 본 뒤**
루트 안인지 확인한다.

사용자에게 보이는 경로는 언제나 루트 기준 상대경로다. 서버의 절대경로는 화면
에도 오류 메시지에도 나타나지 않는다 — 드러나면 서버 구조를 알려주는 셈이다.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

#: 루트를 벗어나는 모든 시도에 같은 문구를 쓴다. 이유를 나눠 알려주면 그 자체가
#: 파일 존재 여부를 떠보는 수단이 된다.
OUTSIDE_ROOT = "허용되지 않는 경로입니다"

#: 소스 파일 확장자. 이것과 폴더만 보이고 만들 수 있다.
SOURCE_SUFFIX = ".in"

#: 이름 길이 상한. 대부분의 파일시스템이 255바이트에서 막는다.
MAX_NAME = 255


class InvalidPath(Exception):
    """루트 밖이거나 형식이 잘못된 경로."""


def resolve_in_root(root: Path, path: str) -> Path:
    """사용자가 준 상대경로를 실제 경로로 바꾼다.

    Raises:
        InvalidPath: 루트를 벗어나거나 형식이 잘못됐을 때.
    """
    if "\x00" in path:
        raise InvalidPath(OUTSIDE_ROOT)

    pure = PurePosixPath(path)
    if pure.is_absolute():
        raise InvalidPath(OUTSIDE_ROOT)

    # 문자열 단계에서 정규화한다. `semi/../boron.in` 처럼 루트 안에서 끝나는
    # 것은 허용하고, 밖으로 나가는 것만 막는다.
    parts: list[str] = []
    for part in pure.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise InvalidPath(OUTSIDE_ROOT)
            parts.pop()
            continue
        parts.append(part)

    candidate = root.joinpath(*parts)

    # 심볼릭 링크는 위 검사를 그대로 통과한다. 실제로 따라가 봐야 한다.
    # 아직 없는 파일(새로 만드는 경우)은 존재하는 조상까지만 확인한다.
    probe = candidate
    while not probe.exists():
        if probe == root or probe.parent == probe:
            break
        probe = probe.parent

    try:
        resolved = probe.resolve(strict=False)
        root_resolved = root.resolve(strict=False)
    except OSError as error:
        raise InvalidPath(OUTSIDE_ROOT) from error

    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise InvalidPath(OUTSIDE_ROOT)

    return candidate


def relative_to_root(root: Path, path: Path) -> str:
    """사용자에게 보여줄 루트 기준 경로. 언제나 `/` 로 구분한다."""
    return path.relative_to(root).as_posix() if path != root else ""


def validate_name(name: str) -> None:
    """새로 만들 파일·폴더 이름을 검사한다.

    Raises:
        InvalidPath: 쓸 수 없는 이름일 때.
    """
    if not name or not name.strip():
        raise InvalidPath("이름을 입력해 주세요")
    if len(name.encode()) > MAX_NAME:
        raise InvalidPath("이름이 너무 깁니다")
    if name in (".", ".."):
        raise InvalidPath("쓸 수 없는 이름입니다")
    if "/" in name or "\\" in name or "\x00" in name:
        raise InvalidPath("이름에 경로 구분자를 넣을 수 없습니다")
    if name.startswith("."):
        # 숨김 파일은 목록에 안 보이는데 용량은 차지한다.
        raise InvalidPath("점으로 시작하는 이름은 쓸 수 없습니다")


def is_source_file(path: str | Path) -> bool:
    """소스 파일(`.in`)인가. 대소문자는 가리지 않는다."""
    return PurePosixPath(str(path)).suffix.lower() == SOURCE_SUFFIX
