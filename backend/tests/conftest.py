from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import PostgresDsn

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
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
