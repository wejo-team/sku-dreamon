"""전역 CORS와 원래 연결 IP를 기준으로 한 단일 프록시 신뢰 경계를 제공한다."""

from ipaddress import ip_address, ip_network

from fastapi import FastAPI
from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings


class ProxyBoundary:
    """Uvicorn의 proxy_headers=False와 함께 원래 TCP peer만 신뢰한다.

    단일 Nginx가 X-Forwarded-For를 연결 IP 하나로 덮어써야 한다.
    이미 Uvicorn에서 전달 IP로 바꾼 scope는 신뢰 peer 검사에서 거부된다.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.production = settings.app_env == "production"
        self.trusted = tuple(
            ip_network(value) for value in settings.http_trusted_proxies
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        forwarded_headers = [
            name
            for name, _ in scope["headers"]
            if name == b"forwarded" or name.startswith(b"x-forwarded-")
        ]
        if not forwarded_headers and not self.production:
            await self.app(scope, receive, send)
            return
        peer = scope.get("client")
        try:
            address = ip_address(peer[0]) if peer else None
            values = headers.getlist("x-forwarded-for")
            protocols = headers.getlist("x-forwarded-proto")
            valid = (
                address is not None
                and any(address in network for network in self.trusted)
                and set(forwarded_headers) == {b"x-forwarded-for", b"x-forwarded-proto"}
                and len(values) == len(protocols) == 1
                and protocols[0] == "https"
                and values[0] == str(ip_address(values[0]))
            )
        except ValueError:
            valid = False
        if not valid:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse(
                    {"detail": "Invalid proxy boundary"}, status_code=400
                )(scope, receive, send)
            return
        # 원본 scope·headers는 외부 middleware와 공유하므로 복사본만 바꾼다.
        forwarded_scope = dict(scope)
        forwarded_scope["client"] = (values[0], 0)
        forwarded_scope["scheme"] = "wss" if scope["type"] == "websocket" else "https"
        await self.app(forwarded_scope, receive, send)


class DeploymentFastAPI(FastAPI):
    """FastAPI 인터페이스를 유지하면서 ServerErrorMiddleware 밖에 CORS를 둔다."""

    def build_middleware_stack(self) -> ASGIApp:
        settings: Settings = self.state.settings
        inner = super().build_middleware_stack()
        inner = CORSMiddleware(
            inner,
            allow_origins=settings.auth_allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
        if settings.http_allowed_hosts:
            inner = TrustedHostMiddleware(
                inner, allowed_hosts=settings.http_allowed_hosts, www_redirect=False
            )
        return ProxyBoundary(inner, settings)
