#!/bin/sh
# JSON을 shell로 읽지 않고 표준 라이브러리 배포 엔진에 인수를 전달한다.
set -eu
exec python3 "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/release.py" "$@"
