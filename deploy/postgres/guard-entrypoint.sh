#!/bin/sh
# UUID 경로로 선택한 장치와 다른 데이터 bind mount에서 DB 생성을 막는다.
set -eu
fail() { printf '%s\n' 'PostgreSQL data mount or runtime TLS validation failed' >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail
[ "${PGDATA:-}" = /var/lib/postgresql/data ] || fail
[ -n "${POSTGRES_FILESYSTEM_UUID:-}" ] || fail
device=/run/db-filesystem-device
[ -b "$device" ] && [ -d "$PGDATA" ] || fail
hex_major=$(stat -c '%t' "$device") || fail
hex_minor=$(stat -c '%T' "$device") || fail
device_id="$((0x$hex_major)):$((0x$hex_minor))"
mount_id=$(awk -v target="$PGDATA" '$5 == target { n++; value=$3 } END { if (n == 1) print value; else exit 1 }' /proc/self/mountinfo) || fail
/usr/local/bin/check-identity.sh "$device_id" "$mount_id" || fail
[ -w "$PGDATA" ] || fail
# root 전용 공급 파일을 PostgreSQL의 엄격한 TLS 키 권한으로 복사한다.
install -d -m 700 -o postgres -g postgres /run/postgresql/tls
install -m 600 -o postgres -g postgres /run/config/postgres.key /run/postgresql/tls/server.key
install -m 644 -o postgres -g postgres /run/config/postgres.crt /run/postgresql/tls/server.crt
install -d -m 700 -o postgres -g postgres /run/postgresql/secrets
install -m 600 -o postgres -g postgres /run/secrets/app-password /run/postgresql/secrets/app-password
install -m 600 -o postgres -g postgres /run/secrets/migration-password /run/postgresql/secrets/migration-password
exec /usr/local/bin/docker-entrypoint.sh "$@"
