#!/bin/sh
# UUID와 실제 마운트의 장치 번호가 모두 같아야 시작을 허용한다.
set -eu
if [ "$#" -ne 4 ] || [ -z "$1" ] || [ "$1" != "$2" ] \
    || [ -z "$3" ] || [ "$3" != "$4" ]; then
    printf '%s\n' 'PostgreSQL filesystem identity check failed' >&2
    exit 1
fi
