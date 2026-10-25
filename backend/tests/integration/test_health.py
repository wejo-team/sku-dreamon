"""DB 없이 동작하는 상태 확인 API와 없는 경로의 404 응답을 검증한다."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_health_does_not_require_a_database(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unknown_endpoint_returns_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/missing")

    assert response.status_code == 404
