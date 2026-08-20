#!/usr/bin/env bash
#
# 루트리스 podman 이 뜨지 못할 때 되살린다.
#
# 증상 (podman 이 내는 원문):
#     running `/usr/bin/newuidmap ...`: write to uid_map failed: Operation not permitted
#     invalid internal status, try resetting the pause process with "podman system migrate"
#
# **podman 이 권하는 `podman system migrate` 를 그대로 따르면 안 된다.**
# 그 명령은 도는 컨테이너를 전부 멈추는데, tcad-postgres 와 tcad-redis 는
# systemd 가 관리하지 않아 스스로 돌아오지 않는다. 앱이 통째로 죽는다.
#
# 여기서는 최소한만 한다 — 근거는 backend/app/runner/podman_health.py 참조.
#
# 사용법:
#   deploy/repair-podman.sh          점검하고, 고장났을 때만 손댄다
#   deploy/repair-podman.sh --force  podman 이 떠 있어도 pause 를 새로 만든다
set -euo pipefail

cd "$(dirname "$0")/.."

# XDG_RUNTIME_DIR 은 로그인 셸이 아닌 곳에서 비어 있다(편집기 터미널, cron,
# 원격 실행). podman 과 같은 방식으로 되짚어 준다 — 이게 비면 pause.pid 를
# 엉뚱한 곳에서 찾는다.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

force=0
[[ "${1:-}" == "--force" ]] && force=1

healthy() { podman info --format '{{.Host.Security.Rootless}}' >/dev/null 2>&1; }

repair() {
    # `-m` 은 cwd 에서 패키지를 찾는다. backend 안에서 돌려야 app 이 보인다.
    ( cd backend && .venv/bin/python -m app.runner.podman_health )
}

echo "== 상태 =="
if healthy && (( ! force )); then
    echo "podman 정상 — 손댈 것이 없습니다."
    echo "  (그래도 새로 만들려면 --force)"
else
    if (( force )); then
        echo "--force: pause 프로세스를 새로 만듭니다."
    else
        echo "podman 이 뜨지 못합니다. 되살립니다."
    fi
    repair
    if healthy; then
        echo "되살렸습니다."
    else
        echo "아직 뜨지 못합니다. 남은 pause 프로세스:" >&2
        pgrep -a -x catatonit >&2 || echo "  (없음)" >&2
        echo "로그아웃 후 다시 로그인하거나, 도는 컨테이너를 직접 멈춘 뒤" >&2
        echo "podman system migrate 를 쓰세요." >&2
        exit 1
    fi
fi

echo
echo "== 점검 =="
# podman 은 XDG_RUNTIME_DIR 이 비어 있는 상태에서 처음 실행되면 runroot 을
# /tmp 밑으로 잡고, 그 값이 DB 에 박힌다. systemd-tmpfiles 는 /tmp 를 부팅
# 때 비우고 오래된 파일을 매일 지우므로, 그 밑에 있으면 도는 컨테이너의
# 런타임 상태가 밖에서 삭제될 수 있다.
runroot=$(podman info --format '{{.Store.RunRoot}}' 2>/dev/null || echo "")
case "$runroot" in
    /tmp/*)
        echo "경고: runroot 이 /tmp 밑에 있습니다 ($runroot)"
        echo "  systemd-tmpfiles 가 여기를 청소하면 도는 컨테이너가 깨집니다."
        echo "  고치려면 ~/.config/containers/storage.conf 에"
        echo "    [storage]"
        echo "    runroot = \"/run/user/$(id -u)/containers\""
        echo "  를 넣으세요. **도는 컨테이너를 전부 새로 띄워야 합니다.**"
        ;;
    "") echo "runroot 을 확인하지 못했습니다" ;;
    *)  echo "runroot 정상: $runroot" ;;
esac

count=$(pgrep -c -x catatonit || true)
if [[ "${count:-0}" -gt 1 ]]; then
    echo "pause 프로세스가 ${count} 개 있습니다 (정상은 1 개)."
    echo "  중복 자체는 무해합니다 — 같은 네임스페이스를 함께 붙들고 있을 뿐입니다."
fi

echo
echo "== 도는 컨테이너 (건드리지 않았습니다) =="
podman ps --format '{{.Names}}\t{{.Status}}'
