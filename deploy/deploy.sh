#!/usr/bin/env bash
#
# TCAD 배포.
#
#   ./deploy/deploy.sh
#
# 레포에서 빌드해 /srv/tcad 로 옮기고, 마이그레이션을 걸고, 서비스를 재시작한다.
# 처음 한 번은 deploy/bootstrap.sh 를 먼저 돌려야 한다.
#
# 순서가 중요하다:
#   1. 마이그레이션을 **먼저** 건다. 새 컬럼을 쓰는 코드가 먼저 뜨면 그 사이
#      요청이 전부 500 이 된다.
#   2. 워커를 먼저 멈춘다. 배포 중에 잡을 집어가면 옛 코드로 실행된다.
#   3. 프론트엔드를 마지막에 바꾼다. 새 화면이 아직 없는 API 를 부르면 안 된다.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${TCAD_TARGET:-/srv/tcad}"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }

if [[ ! -d "$TARGET" ]]; then
    echo "설치 경로가 없습니다: $TARGET" >&2
    echo "먼저 deploy/bootstrap.sh 를 실행하세요." >&2
    exit 1
fi

log "테스트"
# 깨진 것을 배포하지 않는다. 여기서 멈추는 편이 롤백보다 싸다.
(cd "$REPO_ROOT/backend" && .venv/bin/python -m pytest -q --no-header)

log "프론트엔드 빌드"
(cd "$REPO_ROOT/frontend" && npm ci --silent && npm run build)

log "백엔드 동기화"
rsync -a --delete \
    --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' \
    --exclude 'var' \
    "$REPO_ROOT/backend/" "$TARGET/backend/"

log "시뮬레이터 동기화"
rsync -a --delete "$REPO_ROOT/SUPREM4GS/" "$TARGET/SUPREM4GS/"

log "의존성 설치"
"$TARGET/backend/.venv/bin/pip" install --quiet --upgrade \
    -e "$TARGET/backend"

log "워커 정지"
# 마이그레이션 중에 잡을 집어가면 옛 스키마로 돌아간다.
systemctl --user stop tcad-worker

log "마이그레이션"
(cd "$TARGET/backend" && \
    set -a && . "$HOME/.config/tcad/api.env" && set +a && \
    "$TARGET/backend/.venv/bin/python" -m alembic upgrade head)

log "샌드박스 이미지 재빌드"
podman build -t tcad/suprem:latest \
    -f "$TARGET/docker/suprem/Containerfile" "$TARGET"

log "API 재시작"
systemctl --user restart tcad-api

log "프론트엔드 배치"
rsync -a --delete "$REPO_ROOT/frontend/dist/" "$TARGET/frontend/"

log "워커 시작"
systemctl --user start tcad-worker

log "상태 확인"
sleep 3
if curl -fsS http://127.0.0.1:8000/api/health > /dev/null; then
    echo "API 정상"
else
    echo "API 응답 없음 — journalctl --user -u tcad-api -n 50" >&2
    exit 1
fi
systemctl --user is-active tcad-worker > /dev/null && echo "워커 정상"

log "완료"
