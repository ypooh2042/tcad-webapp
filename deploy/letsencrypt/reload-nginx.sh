#!/bin/sh
#
# 인증서가 갱신되면 nginx 를 리로드한다.
#
# 설치:
#   sudo cp deploy/letsencrypt/reload-nginx.sh \
#           /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
#   sudo chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
#
# 확인:
#   sudo certbot renew --dry-run
#
# **왜 필요한가**
#
# `certbot certonly` 로 받은 인증서에는 installer 가 없다. certbot 은 파일만
# 새로 쓰고 nginx 에게 알리지 않는다. nginx 는 기동 시 읽어 둔 인증서를 계속
# 쓰므로, 갱신은 성공하는데 서비스는 옛 인증서를 내보낸다.
#
# 그 상태로 90일째가 되면 사이트가 TLS 오류로 죽는다. 그때까지 아무 경고도
# 없고 `certbot certificates` 는 멀쩡해 보인다 — 원인을 찾기 가장 나쁜 종류의
# 실패다.
#
# `--nginx` 로 받은 인증서(installer = nginx)는 certbot 이 알아서 리로드한다.
# 이 훅은 그 경우에도 해가 없다(리로드가 한 번 더 될 뿐이다).
#
# 이 디렉토리의 훅은 **갱신이 실제로 일어났을 때만** 실행된다. 아직 만료가
# 멀어 갱신을 건너뛴 경우에는 돌지 않으므로, 12시간마다 nginx 가 리로드되는
# 일은 없다.

set -e

# 설정이 깨진 상태로 리로드하면 nginx 가 옛 설정을 유지한 채 오류만 남긴다.
# 먼저 검사해서, 문제가 있으면 갱신 로그에 이유가 남게 한다.
if ! nginx -t; then
    echo "nginx 설정이 올바르지 않아 리로드하지 않았습니다." >&2
    exit 1
fi

systemctl reload nginx
