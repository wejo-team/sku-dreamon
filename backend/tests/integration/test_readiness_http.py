"""준비 검사의 안전한 실패·전체 제한 시간·모델 무호출 계약을 검증한다."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db.session import Database
from app.main import create_app
from app.security.passwords import PasswordBlocklist

pytestmark = pytest.mark.integration


def ready_app(tmp_path: Path) -> FastAPI:
    path = tmp_path / "blocklist.txt"
    path.write_text("blocked-password\n")
    settings = Settings(
        csrf_signing_key=SecretStr("synthetic-signing-key-for-unit-tests"),
        auth_allowed_origins=("https://www.example.com",),
        password_blocklist_path=path,
        password_blocklist_version="test-v1",
        _env_file=None,
    )
    app = create_app(settings)
    app.state.password_blocklist = PasswordBlocklist.from_file(path, version="test-v1")
    app.state.ai_driver = None
    return app


@pytest.mark.parametrize(
    "revision,status",
    [
        ("20261026_09", 200),
        ("20261031_10", 200),
        ("future-unapproved", 503),
        (None, 503),
    ],
)
async def test_readiness_requires_release_compatible_schema(
    tmp_path: Path, revision: str | None, status: int
) -> None:
    app = ready_app(tmp_path)
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = Mock(
        all=Mock(return_value=[] if revision is None else [revision])
    )

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    app.state.database = cast(Database, SimpleNamespace(session=sessions))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/ready")
    assert response.status_code == status
    assert response.json() == {"status": "ready" if status == 200 else "unavailable"}
    assert response.headers["cache-control"] == "no-store"
    session.execute.assert_awaited_once()


async def test_slow_database_probe_is_bounded_and_safe(tmp_path: Path) -> None:
    app = ready_app(tmp_path)
    app.state.settings.readiness_timeout_seconds = 0.1

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        await asyncio.sleep(5)
        raise RuntimeError("secret database url")
        yield AsyncMock(spec=AsyncSession)

    app.state.database = cast(Database, SimpleNamespace(session=sessions))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with asyncio.timeout(0.5):
            response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    assert "secret" not in response.text


async def test_slow_probe_cleanup_cannot_extend_readiness_response_budget(
    tmp_path: Path,
) -> None:
    app = ready_app(tmp_path)
    app.state.settings.readiness_timeout_seconds = 0.1
    closed = asyncio.Event()
    started = 0
    session = AsyncMock(spec=AsyncSession)

    async def slow_execute(*args: object) -> None:
        await asyncio.sleep(5)

    session.execute.side_effect = slow_execute

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        nonlocal started
        started += 1
        try:
            yield session
        finally:
            await asyncio.sleep(0.3)
            closed.set()

    app.state.database = cast(Database, SimpleNamespace(session=sessions))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with asyncio.timeout(0.25):
            response = await client.get("/api/v1/ready")
            for _ in range(5):
                assert (await client.get("/api/v1/ready")).status_code == 503
    assert response.status_code == 503
    assert started == 1
    assert not closed.is_set()
    assert await app.state.readiness_probe.close(0.6)
    assert closed.is_set()


async def test_missing_blocklist_and_ai_client_are_not_ready(tmp_path: Path) -> None:
    app = ready_app(tmp_path)
    app.state.settings.openai_api_key = SecretStr("synthetic-unit-test-key")
    app.state.password_blocklist = None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/ready")
    assert response.status_code == 503


@pytest.mark.parametrize(
    "broken",
    [
        "blocklist_version",
        "empty_blocklist",
        "origins",
        "signing_key",
        "required_ai",
        "ai_client",
    ],
)
async def test_readiness_rejects_invalid_local_state_without_a_database_probe(
    tmp_path: Path, broken: str
) -> None:
    app = ready_app(tmp_path)
    probe = AsyncMock()
    app.state.database = cast(Database, SimpleNamespace(session=probe))
    if broken == "blocklist_version":
        app.state.settings.password_blocklist_version = "unloaded-v2"
    elif broken == "empty_blocklist":
        app.state.password_blocklist = PasswordBlocklist("test-v1", frozenset())
    elif broken == "origins":
        app.state.settings.auth_allowed_origins = ()
    elif broken == "signing_key":
        app.state.settings.csrf_signing_key = None
    elif broken == "required_ai":
        app.state.settings.ai_required = True
    else:
        app.state.settings.openai_api_key = SecretStr("synthetic-key")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    probe.assert_not_called()


async def test_ai_readiness_checks_only_local_client_state_and_makes_zero_requests(
    tmp_path: Path,
) -> None:
    app = ready_app(tmp_path)
    app.state.settings.ai_required = True
    app.state.settings.openai_api_key = SecretStr("synthetic-key")
    request = AsyncMock(
        side_effect=AssertionError("Readiness must not call a provider")
    )
    closed = Mock(return_value=False)
    app.state.ai_driver = SimpleNamespace(
        model=SimpleNamespace(
            root_async_client=SimpleNamespace(is_closed=closed, request=request)
        )
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = Mock(all=Mock(return_value=["20261026_09"]))

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield session

    app.state.database = cast(Database, SimpleNamespace(session=sessions))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        ready = await client.get("/api/v1/ready")
        closed.return_value = True
        unavailable = await client.get("/api/v1/ready")
    assert ready.status_code == 200
    assert unavailable.status_code == 503
    request.assert_not_called()
