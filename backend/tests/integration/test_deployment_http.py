"""CORS 오류 응답과 단일 프록시의 전달 헤더 경계를 DB 없이 검증한다."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from fastapi import Depends, HTTPException, Request
from httpx import ASGITransport, AsyncClient
from pydantic import PostgresDsn, SecretStr
from starlette.responses import StreamingResponse
from starlette.types import ASGIApp
from uvicorn._types import ASGI3Application
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import Settings
from app.core.db.session import Database
from app.dependencies.csrf import require_csrf
from app.main import create_app
from tests.unit.test_deployment_settings import production_settings

ORIGIN = "https://www.example.com"
pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "path,expected",
    [("/denied", 401), ("/csrf", 403), ("/broken", 500), ("/stream", 200)],
)
async def test_allowed_origin_can_read_errors_and_sse(path: str, expected: int) -> None:
    app = create_app(Settings(auth_allowed_origins=(ORIGIN,), _env_file=None))

    @app.get("/denied")
    async def denied() -> None:
        raise HTTPException(401)

    @app.post("/csrf")
    async def csrf() -> None:
        raise HTTPException(403)

    @app.get("/broken")
    async def broken() -> None:
        raise RuntimeError("private error")

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            yield "data: safe\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://api.example.com",
    ) as client:
        response = await client.request(
            "POST" if path == "/csrf" else "GET", path, headers={"Origin": ORIGIN}
        )
    assert response.status_code == expected
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "Origin" in response.headers["vary"]
    if expected == 500:
        assert "private error" not in response.text


async def test_preflight_is_exact_and_does_not_accept_preview_origins() -> None:
    app = create_app(Settings(auth_allowed_origins=(ORIGIN,), _env_file=None))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        good = await client.options(
            "/api/v1/auth/logout",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        bad = await client.options(
            "/api/v1/auth/logout",
            headers={
                "Origin": "https://preview.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        header = await client.options(
            "/api/v1/auth/logout",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-forwarded-for",
            },
        )
    assert good.status_code == 200
    assert good.headers["access-control-allow-origin"] == ORIGIN
    assert bad.status_code == 400
    assert "access-control-allow-origin" not in bad.headers
    assert header.status_code == 400


async def test_cross_origin_csrf_cookie_and_exact_origin_are_preserved() -> None:
    app = create_app(
        Settings(
            csrf_signing_key=SecretStr(
                "synthetic-cors-test-signing-key-at-least-32-bytes"
            ),
            auth_allowed_origins=(ORIGIN,),
            _env_file=None,
        )
    )
    # 익명 CSRF 경로는 DB를 조회하지 않는다. 접근 시 실패하도록 세션을 공급하지 않는다.
    app.state.database = cast(Database, object())

    @app.post("/protected", dependencies=[Depends(require_csrf)])
    async def protected() -> dict[str, str]:
        return {"status": "accepted"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        token_response = await client.get(
            "/api/v1/auth/csrf", headers={"Origin": ORIGIN}
        )
        token = token_response.json()["data"]["csrfToken"]
        accepted = await client.post(
            "/protected", headers={"Origin": ORIGIN, "X-CSRF-Token": token}
        )
        missing = await client.post("/protected", headers={"Origin": ORIGIN})
        foreign = await client.post(
            "/protected",
            headers={"Origin": "https://preview.example.com", "X-CSRF-Token": token},
        )
    assert token_response.status_code == 200
    cookie = token_response.headers["set-cookie"]
    assert "__Host-sku-dreamon-csrf=" in cookie
    assert (
        "HttpOnly" in cookie
        and "Secure" in cookie
        and "SameSite=lax" in cookie
        and "Path=/" in cookie
    )
    assert "Domain=" not in cookie
    assert accepted.status_code == 200
    assert missing.status_code == 403
    assert missing.headers["access-control-allow-origin"] == ORIGIN
    assert foreign.status_code == 403
    assert "access-control-allow-origin" not in foreign.headers


def test_production_http_app_requires_web_configuration(tmp_path: Path) -> None:
    settings = Settings(
        app_env="production",
        database_url=PostgresDsn(
            "postgresql+asyncpg://synthetic:synthetic@postgres/app"
        ),
        database_tls_ca_file=tmp_path / "synthetic-ca.pem",
        _env_file=None,
    )
    with pytest.raises(ValueError, match="production HTTP"):
        create_app(settings)


@pytest.mark.parametrize(
    "peer,forwarded,status",
    [
        ("192.0.2.10", "198.51.100.10", 200),
        ("198.51.100.10", "198.51.100.10", 400),
        ("192.0.2.10", "198.51.100.10, 203.0.113.1", 400),
    ],
)
async def test_forwarding_requires_the_original_trusted_peer(
    peer: str, forwarded: str, status: int
) -> None:
    app = create_app(
        Settings(
            http_trusted_proxies=("192.0.2.10",),
            http_allowed_hosts=("api.example.com",),
            _env_file=None,
        )
    )

    @app.get("/peer")
    async def read_peer(request: Request) -> dict[str, str]:
        assert request.client is not None
        return {"peer": request.client.host, "scheme": request.url.scheme}

    async with AsyncClient(
        transport=ASGITransport(app=app, client=(peer, 1234)),
        base_url="http://api.example.com",
    ) as client:
        response = await client.get(
            "/peer",
            headers={"X-Forwarded-For": forwarded, "X-Forwarded-Proto": "https"},
        )
        bad_host = await client.get(
            "/api/v1/health", headers={"Host": "evil.example.com"}
        )
    assert response.status_code == status
    if status == 200:
        assert response.json() == {"peer": "198.51.100.10", "scheme": "https"}
    assert bad_host.status_code == 400


async def test_production_requires_forwarding_even_for_internal_probes(
    tmp_path: Path,
) -> None:
    app = create_app(production_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("192.0.2.10", 1234)),
        base_url="http://api.example.com",
    ) as client:
        direct = await client.get("/api/v1/health")
        via_proxy = await client.get(
            "/api/v1/health",
            headers={"X-Forwarded-For": "198.51.100.20", "X-Forwarded-Proto": "https"},
        )
    assert direct.status_code == 400
    assert via_proxy.status_code == 200


async def test_already_processed_uvicorn_forwarding_is_rejected(tmp_path: Path) -> None:
    app = ProxyHeadersMiddleware(
        cast(ASGI3Application, create_app(production_settings(tmp_path))),
        trusted_hosts=["192.0.2.10"],
    )
    async with AsyncClient(
        transport=ASGITransport(app=cast(ASGIApp, app), client=("192.0.2.10", 1234)),
        base_url="http://api.example.com",
    ) as client:
        response = await client.get(
            "/api/v1/health",
            headers={"X-Forwarded-For": "198.51.100.20", "X-Forwarded-Proto": "https"},
        )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "headers",
    [
        [
            ("X-Forwarded-For", "198.51.100.20"),
            ("X-Forwarded-For", "198.51.100.21"),
            ("X-Forwarded-Proto", "https"),
        ],
        [("X-Forwarded-For", "198.51.100.20"), ("X-Forwarded-Proto", "http")],
        [
            ("X-Forwarded-For", "198.51.100.20"),
            ("X-Forwarded-Proto", "https"),
            ("Forwarded", "for=198.51.100.20"),
        ],
        [
            ("X-Forwarded-For", "198.51.100.20"),
            ("X-Forwarded-Proto", "https"),
            ("X-Forwarded-Host", "evil.example.com"),
        ],
    ],
)
async def test_production_rejects_ambiguous_proxy_headers(
    tmp_path: Path, headers: list[tuple[str, str]]
) -> None:
    app = create_app(production_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("192.0.2.10", 1234)),
        base_url="http://api.example.com",
    ) as client:
        response = await client.get("/api/v1/health", headers=headers)
    assert response.status_code == 400


def test_supported_server_launch_disables_uvicorn_forwarding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import Mock

    from app.cli.serve import main

    run = Mock()
    monkeypatch.setattr("app.cli.serve.uvicorn.run", run)
    main()
    assert run.call_args.kwargs["proxy_headers"] is False
    assert run.call_args.kwargs["forwarded_allow_ips"] == ""
