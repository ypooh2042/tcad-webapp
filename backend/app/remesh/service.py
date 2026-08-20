"""`.str` → 새 메시 → `.str`.

시뮬레이터 코드는 한 줄도 건드리지 않는다. `.str` 이 좌표·영역·삼각형·물성값을
모두 담는 완전한 교환 형식이고 `structure in=` 으로 그대로 이어서 실행되기
때문이다.

gmsh 는 **별도 컨테이너에서 subprocess 로만** 부른다. 우리 코드에 링크하지
않고(GPL), 입력이 사용자 입력에서 파생되므로 suprem 과 같은 격리로 돌린다.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from app.remesh.assemble import assemble
from app.remesh.geo import build_geo
from app.remesh.msh import read_msh
from app.remesh.transfer import Sampler  # noqa: F401 - 의존 관계를 드러낸다
from app.runner.sandbox import SandboxLimits, build_sandbox_argv
from app.str_parser.parser import parse_structure
from app.str_parser.writer import write_structure

DEFAULT_IMAGE = "tcad/remesh"

#: 컨테이너 안에서 쓸 파일 이름. 고정이라 사용자 입력이 인자에 섞이지 않는다.
_GEO = "mesh.geo"
_MSH = "mesh.msh"


@dataclass(frozen=True, slots=True)
class RemeshResult:
    text: str
    old_points: int
    new_points: int
    old_elements: int
    new_elements: int


def remesh(source: str, image: str = DEFAULT_IMAGE,
           limits: SandboxLimits | None = None) -> RemeshResult:
    """`.str` 텍스트를 받아 메시만 새로 짠 `.str` 텍스트를 돌려준다.

    형상은 그대로다 — 바깥 경계와 물질 계면을 제약으로 고정하고 안쪽만 다시
    짠다. 물성값은 옛 메시에서 보간해 싣는다.

    Raises:
        RuntimeError: gmsh 가 메시를 못 만들었을 때. 조용히 옛 것을 돌려주면
            나아진 줄 알고 넘어간다.
    """
    old = parse_structure(source)
    model = build_geo(old)

    with TemporaryDirectory(prefix="remesh-") as tmp:
        workdir = Path(tmp).resolve()
        (workdir / _GEO).write_text(model.to_text())

        argv = list(
            build_sandbox_argv(
                image=image,
                host_workdir=workdir,
                limits=limits or SandboxLimits(timeout_seconds=300),
            )
        ) + ["-2", _GEO, "-format", "msh2", "-o", _MSH]

        completed = subprocess.run(  # noqa: S603 - argv 는 사용자 입력에 의존하지 않는다
            argv, capture_output=True, text=True, check=False
        )
        produced = workdir / _MSH
        if not produced.exists():
            raise RuntimeError(
                "gmsh 가 메시를 만들지 못했습니다\n"
                + (completed.stdout + completed.stderr)[-2000:]
            )
        mesh = read_msh(produced.read_text())

    built = assemble(old, mesh)
    return RemeshResult(
        text=write_structure(built, source),
        old_points=len(old.coordinates),
        new_points=len(built.coordinates),
        old_elements=len(old.elements),
        new_elements=len(built.elements),
    )


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("사용법: python -m app.remesh.service <입력.str> <출력.str>")
        return 2
    if shutil.which("podman") is None:
        print("podman 이 없습니다")
        return 2

    result = remesh(Path(args[0]).read_text())
    Path(args[1]).write_text(result.text)
    print(
        f"점 {result.old_points} → {result.new_points}, "
        f"삼각형 {result.old_elements} → {result.new_elements}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
