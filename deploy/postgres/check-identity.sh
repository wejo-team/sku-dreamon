#!/bin/sh
# 호스트에서 UUID로 선택한 장치와 실제 마운트의 장치 번호가 같아야 시작을 허용한다.
set -eu
if [ "$#" -ne 2 ] || [ -z "$1" ] || [ "$1" != "$2" ]; then
    printf '%s\n' 'PostgreSQL filesystem identity check failed' >&2
    exit 1
fi
