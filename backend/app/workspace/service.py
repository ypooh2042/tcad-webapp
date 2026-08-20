"""사용자 작업공간 — 사용자가 자기 파일시스템으로 인식하는 곳.

루트 하나가 사용자 한 명의 전부다. 그 안에서만 만들고 고치고 지운다. 경로
안전은 paths.py 가 책임진다.

**폴더와 `.in` 파일만** 다룬다. `.str` 은 실행 결과라 여기 목록에도 안 나오고
용량 셈에도 안 들어간다 — 산출물은 캐시로 따로 관리한다. 셈에 넣으면 실행할
수록 소스 저장이 막히는 이상한 일이 생긴다.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.workspace.starter import seed
from app.workspace.paths import (
    InvalidPath,
    is_source_file,
    relative_to_root,
    resolve_in_root,
    validate_name,
)


class WorkspaceNotFound(Exception):
    """없는 파일이나 폴더."""


class WorkspaceConflict(Exception):
    """이미 있는 이름, 또는 할 수 없는 이동."""


class QuotaExceeded(Exception):
    """저장 상한을 넘는 쓰기."""


@dataclass(frozen=True, slots=True)
class Entry:
    #: 루트 기준 경로. 화면에 그대로 쓴다.
    path: str
    name: str
    is_dir: bool
    size_bytes: int


@dataclass(frozen=True, slots=True)
class Usage:
    used_bytes: int
    quota_bytes: int

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.quota_bytes - self.used_bytes)


@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path
    quota_bytes: int

    # ── 조회 ────────────────────────────────────────────────

    def list(self) -> list[Entry]:
        """루트 바로 아래."""
        return self.read_dir("")

    def read_dir(self, path: str) -> list[Entry]:
        target = self._resolve(path)
        if not target.is_dir():
            raise WorkspaceNotFound(path)
        return _sorted(self._entries(target))

    def tree(self) -> list[Entry]:
        """모든 층을 편 목록. 화면에서 트리로 다시 조립한다."""
        found: list[Entry] = []

        def walk(folder: Path) -> None:
            for entry in _sorted(self._entries(folder)):
                found.append(entry)
                if entry.is_dir:
                    walk(self.root / entry.path)

        self._ensure_root()
        walk(self.root)
        return found

    def read(self, path: str) -> str:
        target = self._resolve(path)
        if not target.is_file():
            raise WorkspaceNotFound(path)
        return target.read_text()

    def usage(self) -> Usage:
        return Usage(used_bytes=self._used_bytes(), quota_bytes=self.quota_bytes)

    # ── 변경 ────────────────────────────────────────────────

    def write(self, path: str, content: str) -> None:
        """소스 파일을 만들거나 덮어쓴다.

        Raises:
            InvalidPath: `.in` 이 아닌 경로일 때.
            WorkspaceNotFound: 상위 폴더가 없을 때.
            WorkspaceConflict: 같은 이름의 폴더가 있을 때.
            QuotaExceeded: 상한을 넘길 때.
        """
        if not is_source_file(path):
            raise InvalidPath("소스 파일(.in) 만 저장할 수 있습니다")

        target = self._resolve(path)
        validate_name(target.name)
        if target.is_dir():
            raise WorkspaceConflict(path)
        if not target.parent.is_dir():
            raise WorkspaceNotFound(str(Path(path).parent))

        encoded = content.encode()
        # 덮어쓰기는 차이만 센다. 옛 크기를 빼지 않으면 상한 가까이에서 같은
        # 파일을 다시 저장하는 것조차 막힌다.
        previous = target.stat().st_size if target.is_file() else 0
        if self._used_bytes() - previous + len(encoded) > self.quota_bytes:
            raise QuotaExceeded(path)

        target.write_bytes(encoded)

    def make_folder(self, path: str) -> None:
        target = self._resolve(path)
        validate_name(target.name)
        if target.exists():
            raise WorkspaceConflict(path)
        if not target.parent.is_dir():
            raise WorkspaceNotFound(str(Path(path).parent))
        target.mkdir()

    def rename(self, path: str, destination: str) -> None:
        """이름을 바꾸거나 옮긴다. 둘은 같은 연산이다."""
        source = self._resolve(path)
        if not source.exists():
            raise WorkspaceNotFound(path)

        target = self._resolve(destination)
        validate_name(target.name)

        # 파일은 `.in` 을 유지해야 한다. `.txt` 로 바꾸면 목록에서 사라져
        # 되찾을 길이 없어진다.
        if source.is_file() and not is_source_file(destination):
            raise InvalidPath("소스 파일은 .in 이름을 유지해야 합니다")

        if target.exists():
            raise WorkspaceConflict(destination)
        if not target.parent.is_dir():
            raise WorkspaceNotFound(str(Path(destination).parent))
        # 폴더를 자기 안으로 옮기면 트리가 끊겨 되돌릴 수 없다.
        if source.is_dir() and source in target.parents:
            raise WorkspaceConflict(destination)

        source.rename(target)

    def delete(self, path: str) -> None:
        if not path:
            raise InvalidPath("루트는 지울 수 없습니다")

        target = self._resolve(path)
        if not target.exists():
            raise WorkspaceNotFound(path)

        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    # ── 내부 ────────────────────────────────────────────────

    def _resolve(self, path: str) -> Path:
        self._ensure_root()
        return resolve_in_root(self.root, path)

    def _ensure_root(self) -> None:
        # 가입 직후 첫 요청에서 루트가 없으면 목록부터 실패한다.
        #
        # **처음 만들 때만 예제를 넣는다.** 있을 때마다 확인해서 채워 넣으면
        # 사용자가 지운 예제가 되살아나 지울 방법이 없어진다. mkdir 이
        # 성공했다는 것이 곧 "이 작업공간은 방금 생겼다"는 뜻이다 — 같은 순간에
        # 들어온 다른 요청은 FileExistsError 를 받고 씨앗 뿌리기를 건너뛴다.
        try:
            self.root.mkdir(parents=True)
        except FileExistsError:
            return
        seed(self.root)

    def _entries(self, folder: Path) -> list[Entry]:
        found: list[Entry] = []
        for item in folder.iterdir():
            # 심볼릭 링크는 목록에 올리지 않는다. 따라가면 루트 밖일 수 있고,
            # 사용자가 만들 수단도 없으므로 보일 이유가 없다.
            if item.is_symlink():
                continue
            if item.name.startswith("."):
                continue
            if not item.is_dir() and not is_source_file(item.name):
                continue
            found.append(
                Entry(
                    path=relative_to_root(self.root, item),
                    name=item.name,
                    is_dir=item.is_dir(),
                    size_bytes=0 if item.is_dir() else item.stat().st_size,
                )
            )
        return found

    def _used_bytes(self) -> int:
        """소스 파일 총량. 산출물은 세지 않는다."""
        self._ensure_root()
        total = 0
        for item in self.root.rglob("*"):
            if item.is_symlink() or not item.is_file():
                continue
            if not is_source_file(item.name):
                continue
            total += item.stat().st_size
        return total


def _sorted(entries: list[Entry]) -> list[Entry]:
    """폴더 먼저, 그다음 이름순. 섞여 있으면 구조가 눈에 안 들어온다."""
    return sorted(entries, key=lambda entry: (not entry.is_dir, entry.name.lower()))
