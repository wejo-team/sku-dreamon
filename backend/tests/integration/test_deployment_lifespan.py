"""DB·AI client와 준비 검사 작업의 소유권과 종료 예산을 검증한다."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration


async def test_ai_client_close_timeout_still_disposes_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        openai_api_key=SecretStr("synthetic-lifespan-test-key"),
        shutdown_timeout_seconds=0.1,
        _env_file=None,
    )
    database = SimpleNamespace(engine=SimpleNamespace(dispose=AsyncMock()))
    factory = Mock(return_value=database)
    monkeypatch.setattr("app.main.create_database", factory)

    async def close() -> None:
        await asyncio.sleep(2)

    driver = SimpleNamespace(
        model=SimpleNamespace(root_async_client=SimpleNamespace(close=close))
    )
    monkeypatch.setattr("app.main.OpenAiAgentDriver", Mock(return_value=driver))
    app = create_app(settings)
    with pytest.raises(TimeoutError):
        async with app.router.lifespan_context(app):
            pass
    assert factory.call_args.kwargs["settings"] is settings
    database.engine.dispose.assert_awaited_once()


async def test_failed_ai_initialization_disposes_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        openai_api_key=SecretStr("synthetic-lifespan-test-key"), _env_file=None
    )
    database = SimpleNamespace(engine=SimpleNamespace(dispose=AsyncMock()))
    monkeypatch.setattr("app.main.create_database", Mock(return_value=database))
    monkeypatch.setattr(
        "app.main.OpenAiAgentDriver",
        Mock(side_effect=ValueError("synthetic initialization failure")),
    )
    app = create_app(settings)
    with pytest.raises(ValueError):
        async with app.router.lifespan_context(app):
            pass
    database.engine.dispose.assert_awaited_once()


async def test_cli_passes_full_database_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.cli.ai_runs import cleanup

    settings = Settings(_env_file=None)
    database = SimpleNamespace(engine=SimpleNamespace(dispose=AsyncMock()))
    factory = Mock(return_value=database)
    service = SimpleNamespace(clean_expired=AsyncMock())
    monkeypatch.setattr("app.cli.ai_runs.Settings", Mock(return_value=settings))
    monkeypatch.setattr("app.cli.ai_runs.create_database", factory)
    monkeypatch.setattr("app.cli.ai_runs.RunService", Mock(return_value=service))
    await cleanup()
    assert factory.call_args.kwargs["settings"] is settings
    service.clean_expired.assert_awaited_once()
    database.engine.dispose.assert_awaited_once()
