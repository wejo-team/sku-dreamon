#!/bin/sh
# Certbot의 실제 deploy hook만 인증서 적용 이벤트를 남긴다.
set -eu
case "${RENEWED_LINEAGE:-}" in /etc/letsencrypt/live/*) ;; *) exit 1 ;; esac
[ -r "$RENEWED_LINEAGE/fullchain.pem" ] && [ -r "$RENEWED_LINEAGE/privkey.pem" ]
umask 077
sha256sum "$RENEWED_LINEAGE/fullchain.pem" | cut -d ' ' -f 1 > /run/certbot-events/installed.tmp
mv /run/certbot-events/installed.tmp /run/certbot-events/installed
