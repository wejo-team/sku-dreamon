"""HTTP 초기화 또는 슬롯별 TLS 후보의 전체 Nginx 설정을 생성한다."""

import argparse
import re
from pathlib import Path


def render_config(
    host: str, slot: str, release: str, drain_seconds: int, *, tls: bool
) -> str:
    """외부 문자열이 Nginx 지시문으로 삽입되지 않도록 입력을 제한한다."""
    labels = host.split(".")
    if (
        len(host) > 253
        or len(labels) < 2
        or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        )
    ):
        raise ValueError("Expected an exact lowercase API hostname")
    if slot not in {"app_blue", "app_green"}:
        raise ValueError("Expected a deployment slot")
    if not re.fullmatch(r"[0-9a-f]{40}", release):
        raise ValueError("Expected a full release SHA")
    if not 30 <= drain_seconds <= 1800:
        raise ValueError("Expected a bounded drain budget of at least 30 seconds")
    config = f"""# release:{release} slot:{slot}
# 이 파일 전체를 nginx -t로 검사한 뒤 active.conf를 원자적으로 교체한다.
user nginx;
worker_processes 1;
pid /var/run/nginx.pid;
error_log /dev/stderr warn;
worker_shutdown_timeout {drain_seconds + 15}s;
events {{ worker_connections 1024; }}
http {{
    log_format minimal '$remote_addr $request_method $uri $status $request_time';
    access_log /dev/stdout minimal;
    server_tokens off;
    client_max_body_size 1m;
    client_header_timeout 15s;
    client_body_timeout 60s;
    keepalive_timeout 10s;
    gzip off;
    server {{ listen 80 default_server; server_name _; return 444; }}
    server {{
        listen 80;
        server_name {host};
        location ^~ /.well-known/acme-challenge/ {{
            root /var/www/acme;
            default_type text/plain;
            try_files $uri =404;
        }}
        location / {{ return 308 https://{host}$request_uri; }}
    }}
"""
    if tls:
        # 정적 upstream 이름은 후보 검사와 reload 시점마다 Docker DNS로 해석한다.
        config += f"""    upstream active_api {{ server {slot}:8000; }}
    server {{
        listen 443 ssl default_server;
        ssl_reject_handshake on;
        server_name _;
        return 444;
    }}
    server {{
        listen 443 ssl;
        server_name {host};
        ssl_certificate /etc/letsencrypt/live/{host}/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/{host}/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        location = /api/v1/ready {{ return 404; }}
        location ^~ /api/v1/ready/ {{ return 404; }}
        location / {{
            proxy_pass http://active_api;
            proxy_http_version 1.1;
            proxy_buffering off;
            proxy_request_buffering off;
            proxy_cache off;
            proxy_next_upstream off;
            proxy_connect_timeout 3s;
            proxy_send_timeout {drain_seconds}s;
            proxy_read_timeout {drain_seconds}s;
            send_timeout {drain_seconds}s;
            # 임의의 Forwarded/X-Forwarded-*를 포함해 외부 헤더를 먼저 제거한다.
            proxy_pass_request_headers off;
            proxy_set_header Host {host};
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header Connection "";
            proxy_set_header Accept $http_accept;
            proxy_set_header Accept-Language $http_accept_language;
            proxy_set_header Content-Type $http_content_type;
            proxy_set_header Cookie $http_cookie;
            proxy_set_header Origin $http_origin;
            proxy_set_header Access-Control-Request-Method $http_access_control_request_method;
            proxy_set_header Access-Control-Request-Headers $http_access_control_request_headers;
            proxy_set_header Referer $http_referer;
            proxy_set_header User-Agent $http_user_agent;
            proxy_set_header X-CSRF-Token $http_x_csrf_token;
            proxy_set_header Authorization $http_authorization;
            proxy_set_header If-Match $http_if_match;
            proxy_set_header If-None-Match $http_if_none_match;
            proxy_set_header If-Modified-Since $http_if_modified_since;
            proxy_hide_header X-Release-ID;
            proxy_hide_header X-Release-Slot;
            add_header X-Release-ID {release} always;
            add_header X-Release-Slot {slot} always;
        }}
    }}
"""
    return config + "}\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--slot", choices=("app_blue", "app_green"))
    parser.add_argument("--release")
    parser.add_argument("--drain-seconds", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tls", action="store_true")
    args = parser.parse_args()
    if args.tls and (not args.slot or not args.release):
        parser.error("TLS requires an explicit slot and release")
    try:
        config = render_config(
            args.host,
            args.slot or "app_blue",
            args.release or "0" * 40,
            args.drain_seconds,
            tls=args.tls,
        )
    except ValueError as error:
        parser.error(str(error))
    args.output.write_text(config, encoding="utf-8")


if __name__ == "__main__":
    main()
