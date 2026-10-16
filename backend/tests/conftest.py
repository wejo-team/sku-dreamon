from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pydantic import PostgresDsn

from app.core.config import Settings
from app.factory import create_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(
        database_url=PostgresDsn(
            "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"
        ),
        _env_file=None,
    )
    app = create_app(settings)
    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app), base_url="http://test"
        ) as client:
            yield client
