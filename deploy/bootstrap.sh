#!/usr/bin/env bash
#
# TCAD 최초 설치. 한 번만 돌린다.
#
#   ./deploy/bootstrap.sh
#
# **이 스크립트는 sudo 를 쓰지 않는다.**
#
# 권한이 필요한 일은 두 가지뿐이고, 그것만 미리 손으로 해 두면 나머지는 전부
# 사용자 권한으로 돌아간다. 스크립트 안에서 sudo 를 부르면 비대화형 환경
# (CI, 편집기 터미널, 원격 실행)에서 비밀번호 프롬프트에 걸려 멈춘다.
#
# 이 스크립트가 하지 **않는** 것:
#   - DNS A 레코드 (tcad.ypooh2062.link → 이 서버 공인 IP)
#   - 설치 경로 생성과 linger (아래에서 필요한 명령을 알려준다)
#   - nginx 설정 배치와 인증서 발급 (끝에 안내가 출력된다)
#   - 첫 관리자 계정 생성 (끝에 안내가 출력된다)
#
# 비밀번호를 물어보지 않는다. DB 비밀번호는 여기서 만들어 api.env 에 넣는다.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${TCAD_TARGET:-/srv/tcad}"
ENV_FILE="$HOME/.config/tcad/api.env"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }

# systemctl --user 는 사용자 D-Bus 세션을 찾아야 한다. 로그인 셸이 아닌 곳
# (편집기 터미널, cron, 원격 실행)에서는 XDG_RUNTIME_DIR 이 비어 있어서
# "Failed to connect to bus" 로 죽는다. 실제로 그렇게 죽었다.
# 소켓은 linger 가 켜져 있으면 항상 있으므로 직접 채워 준다.
ensure_user_bus() {
    if [[ -z "${XDG_RUNTIME_DIR:-}" ]]; then
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
    fi
    if [[ ! -d "$XDG_RUNTIME_DIR" ]]; then
        echo "사용자 런타임 디렉토리가 없습니다: $XDG_RUNTIME_DIR" >&2
        echo "  로그인 세션에서 실행하거나 linger 를 켜세요:" >&2
        echo "    sudo loginctl enable-linger \"\$USER\"" >&2
        exit 1
    fi
}


log "설치 경로 확인: $TARGET"
if [[ ! -d "$TARGET" || ! -w "$TARGET" ]]; then
    cat >&2 <<PREREQ

설치 경로가 없거나 쓸 수 없습니다: $TARGET

터미널에서 아래 한 줄을 먼저 실행한 뒤 이 스크립트를 다시 돌리세요.
(nginx 가 정적 파일을 읽어야 하므로 홈 디렉토리가 아니라 /srv 를 씁니다.
 홈은 보통 750 이라 nginx 사용자가 통과하지 못합니다.)

    sudo mkdir -p "$TARGET" && sudo chown "\$USER:\$USER" "$TARGET"

PREREQ
    exit 1
fi
mkdir -p "$TARGET"/{backend,frontend,var/jobs,docker}

log "PostgreSQL·Redis 확인"
# 이 서버에는 다른 서비스도 돈다. 기존 인스턴스를 쓸지 새로 띄울지는 상황에
# 따라 다르므로 여기서는 확인만 하고 안내한다.
#
# **볼륨 이름을 개발용과 반드시 다르게 한다.** compose.dev.yml 이 쓰는
# tcad-pgdata 를 그대로 쓰면 두 postmaster 가 같은 데이터 디렉토리를 잡는다.
# 컨테이너마다 PID 네임스페이스가 달라 postmaster.pid 잠금이 서로를 못 보고,
# 둘 다 뜬 채로 크래시 복구를 돌린다 — 실제로 그렇게 띄웠다가 급히 내렸다.
if ! ss -tln 2>/dev/null | grep -q '127.0.0.1:5432'; then
    echo "  5432 에 PostgreSQL 이 없습니다. 컨테이너로 띄우려면:" >&2
    echo "    podman run -d --name tcad-postgres --restart=always \\" >&2
    echo "      -p 127.0.0.1:5432:5432 -e POSTGRES_USER=tcad -e POSTGRES_DB=tcad \\" >&2
    echo "      -e POSTGRES_PASSWORD=<api.env 의 비밀번호> \\" >&2
    echo "      -v tcad-pgdata-prod:/var/lib/postgresql/data \\" >&2
    echo "      docker.io/library/postgres:16-alpine" >&2
    echo "  (POSTGRES_PASSWORD 는 볼륨이 **비어 있을 때만** 적용된다. 이미 쓰던" >&2
    echo "   볼륨을 재사용하면 옛 비밀번호가 그대로다.)" >&2
fi

if ! ss -tln 2>/dev/null | grep -q '127.0.0.1:6379'; then
    echo "  6379 에 Redis 가 없습니다. 컨테이너로 띄우려면:" >&2
    echo "    podman run -d --name tcad-redis --restart=always \\" >&2
    echo "      -p 127.0.0.1:6379:6379 docker.io/library/redis:7-alpine \\" >&2
    echo "      redis-server --save '' --appendonly no" >&2
fi

# 재부팅 후에도 컨테이너가 살아나게 한다. --restart=always 만으로는 부팅 시
# 다시 뜨지 않는다(루트리스 podman 은 데몬이 없다).
systemctl --user enable podman-restart.service > /dev/null 2>&1 || true

log "환경 파일 생성: $ENV_FILE"
if [[ -f "$ENV_FILE" ]]; then
    echo "  이미 있습니다. 건드리지 않습니다."
else
    mkdir -p "$(dirname "$ENV_FILE")"
    # 비밀번호를 손으로 정하면 약해지기 쉽다. 여기서 만든다.
    DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    cat > "$ENV_FILE" <<ENV
# TCAD 운영 설정. 이 파일은 레포에 올리지 않는다.
TCAD_DATABASE_URL=postgresql+asyncpg://tcad:${DB_PASSWORD}@127.0.0.1:5432/tcad
TCAD_REDIS_URL=redis://127.0.0.1:6379/0
TCAD_JOBS_ROOT=${TARGET}/var/jobs
# HTTPS 로만 세션 쿠키를 보낸다. 운영에서 false 로 두면 평문으로 샌다.
TCAD_SESSION_COOKIE_SECURE=true
TCAD_MAX_CONCURRENT_JOBS=4
ENV
    chmod 600 "$ENV_FILE"
    echo "  DB 비밀번호를 생성했습니다. PostgreSQL 계정에도 같은 값을 넣으세요:"
    echo "    ALTER USER tcad WITH PASSWORD '${DB_PASSWORD}';"
fi

log "파이썬 환경"
python3 -m venv "$TARGET/backend/.venv"
"$TARGET/backend/.venv/bin/pip" install --quiet --upgrade pip

log "레포 동기화"
rsync -a --delete --exclude '.venv' --exclude '__pycache__' \
    --exclude 'var' \
    "$REPO_ROOT/backend/" "$TARGET/backend/"
rsync -a --delete "$REPO_ROOT/SUPREM4GS/" "$TARGET/SUPREM4GS/"
rsync -a --delete "$REPO_ROOT/docker/" "$TARGET/docker/"
"$TARGET/backend/.venv/bin/pip" install --quiet -e "$TARGET/backend"

log "샌드박스 이미지 빌드"
podman build -t tcad/suprem:latest \
    -f "$TARGET/docker/suprem/Containerfile" "$TARGET"

log "systemd 사용자 유닛 설치"
ensure_user_bus
mkdir -p "$HOME/.config/systemd/user"
cp "$REPO_ROOT"/deploy/systemd/tcad-*.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload

# 로그아웃해도 서비스가 계속 돌게 한다. 이것만은 권한이 필요하다.
# 안 되어 있어도 지금 당장은 돌아가므로 실패로 처리하지 않고 알려만 준다 —
# SSH 를 끊는 순간 멈추는 것을 나중에 겪는 편이 더 나쁘다.
if [[ "$(loginctl show-user "$USER" --property=Linger --value 2>/dev/null)" != "yes" ]]; then
    LINGER_NEEDED=1
else
    LINGER_NEEDED=0
fi

if [[ "${LINGER_NEEDED:-0}" == "1" ]]; then
    cat <<'LINGER'

⚠ linger 가 꺼져 있습니다. 이대로 두면 로그아웃하는 순간 서비스가 멈춥니다.

    sudo loginctl enable-linger "$USER"

LINGER
fi

cat <<'NEXT'

════════════════════════════════════════════════════════════════
남은 것은 손으로 합니다.

1) DNS A 레코드
     tcad.ypooh2062.link → 이 서버의 공인 IP

2) 데이터베이스 생성 (아직 없다면)
     createdb -U tcad tcad
     # 위에서 출력된 비밀번호를 계정에 설정

3) 마이그레이션
     cd /srv/tcad/backend
     set -a && . ~/.config/tcad/api.env && set +a
     .venv/bin/python -m alembic upgrade head

4) 서비스 시작
     systemctl --user enable --now tcad-api tcad-worker
     systemctl --user status tcad-api

5) nginx + HTTPS
     sudo cp deploy/nginx/tcad.ypooh2062.link.conf /etc/nginx/sites-available/
     sudo ln -s /etc/nginx/sites-available/tcad.ypooh2062.link.conf \
                /etc/nginx/sites-enabled/
     sudo nginx -t
     sudo certbot --nginx -d tcad.ypooh2062.link
     sudo systemctl reload nginx

6) 첫 관리자 (초대를 발급하려면 관리자가 필요하고,
   관리자가 되려면 가입해야 하는 순환을 여기서 끊습니다)
     cd /srv/tcad/backend
     set -a && . ~/.config/tcad/api.env && set +a
     .venv/bin/python -m app.auth.create_user --email <이메일> --admin

7) 프론트엔드 첫 배치
     ./deploy/deploy.sh
════════════════════════════════════════════════════════════════
NEXT
