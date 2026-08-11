#!/usr/bin/env bash
#
# TCAD 최초 설치. 한 번만 돌린다.
#
#   ./deploy/bootstrap.sh
#
# 이 스크립트가 하지 **않는** 것 — 손으로 해야 한다:
#   - DNS A 레코드 (tcad.ypooh2062.link → 이 서버 공인 IP)
#   - nginx 설정 배치와 인증서 발급 (아래 안내가 출력된다)
#   - 첫 관리자 계정 생성 (아래 안내가 출력된다)
#
# 비밀번호를 물어보지 않는다. DB 비밀번호는 여기서 만들어 api.env 에 넣는다.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${TCAD_TARGET:-/srv/tcad}"
ENV_FILE="$HOME/.config/tcad/api.env"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }

log "설치 경로 준비: $TARGET"
sudo mkdir -p "$TARGET"
sudo chown "$USER:$USER" "$TARGET"
mkdir -p "$TARGET"/{backend,frontend,var/jobs,docker}

log "PostgreSQL·Redis 확인"
# 이 서버에는 다른 서비스도 돈다. 기존 인스턴스를 쓸지 새로 띄울지는 상황에
# 따라 다르므로 여기서는 확인만 하고 안내한다.
if ! command -v psql > /dev/null && ! podman ps --format '{{.Names}}' | grep -q postgres; then
    echo "  PostgreSQL 이 보이지 않습니다. 컨테이너로 띄우려면:" >&2
    echo "    podman run -d --name tcad-postgres --restart=always \\" >&2
    echo "      -p 127.0.0.1:5432:5432 -e POSTGRES_USER=tcad -e POSTGRES_DB=tcad \\" >&2
    echo "      -e POSTGRES_PASSWORD=<비밀번호> -v tcad-pgdata:/var/lib/postgresql/data \\" >&2
    echo "      docker.io/library/postgres:16-alpine" >&2
fi

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
    "$REPO_ROOT/backend/" "$TARGET/backend/"
rsync -a --delete "$REPO_ROOT/SUPREM4GS/" "$TARGET/SUPREM4GS/"
rsync -a --delete "$REPO_ROOT/docker/" "$TARGET/docker/"
"$TARGET/backend/.venv/bin/pip" install --quiet -e "$TARGET/backend"

log "샌드박스 이미지 빌드"
podman build -t tcad/suprem:latest \
    -f "$TARGET/docker/suprem/Containerfile" "$TARGET"

log "systemd 사용자 유닛 설치"
mkdir -p "$HOME/.config/systemd/user"
cp "$REPO_ROOT"/deploy/systemd/tcad-*.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
# 로그아웃해도 계속 돌게 한다. 없으면 SSH 를 끊는 순간 멈춘다.
sudo loginctl enable-linger "$USER"

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
