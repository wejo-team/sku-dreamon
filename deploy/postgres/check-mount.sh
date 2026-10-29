#!/bin/sh
# 선택한 루트 또는 별도 파일시스템만 확인하며 포맷이나 마운트를 수행하지 않는다.
set -eu
fail() { printf '%s\n' 'Host PostgreSQL filesystem validation failed' >&2; exit 1; }
[ "$#" -eq 3 ] || fail
mount_path=$1
expected_uuid=$2
data_path=$3
[ -n "$expected_uuid" ] && [ "$data_path" != "$mount_path" ] || fail
[ -d "$mount_path" ] && [ -d "$data_path" ] && [ -w "$data_path" ] || fail
[ "$(realpath "$mount_path")" = "$mount_path" ] || fail
[ "$(realpath "$data_path")" = "$data_path" ] || fail
case "$data_path" in "${mount_path%/}"/*) ;; *) fail ;; esac
actual_uuid=$(findmnt --noheadings --raw --mountpoint "$mount_path" --output UUID) || fail
[ "$actual_uuid" = "$expected_uuid" ] || fail
mounted_device=$(findmnt --noheadings --raw --target "$mount_path" --output MAJ:MIN) || fail
data_device=$(findmnt --noheadings --raw --target "$data_path" --output MAJ:MIN) || fail
[ -n "$mounted_device" ] && [ "$mounted_device" = "$data_device" ] || fail
