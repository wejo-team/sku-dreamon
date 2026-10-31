"""격리된 설정의 앱과 수명 주기를 관리하는 HTTP 클라이언트를 제공한다."""

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any, cast

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langsmith import utils as langsmith_utils
from pydantic import PostgresDsn

from app.core.config import Settings


def pytest_configure() -> None:
    """앱 모듈을 수집하기 전에 개발자 추적 키와 dotenv 자동 적용을 차단한다."""
    for name in tuple(os.environ):
        if name.upper().startswith(("LANGSMITH_", "LANGCHAIN_")):
            del os.environ[name]
    os.environ["LANGSMITH_API_KEY"] = ""
    cast(Any, langsmith_utils.get_env_var).cache_clear()


@pytest.fixture(autouse=True)
def isolated_tracing_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in tuple(os.environ):
        if name.upper().startswith(("LANGSMITH_", "LANGCHAIN_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    cast(Any, langsmith_utils.get_env_var).cache_clear()
    try:
        yield
    finally:
        cast(Any, langsmith_utils.get_env_var).cache_clear()


@pytest.fixture
def app() -> FastAPI:
    from app.main import create_app

    settings = Settings(
        database_url=PostgresDsn(
            "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"
        ),
        _env_file=None,
    )
    return create_app(settings)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            yield client
