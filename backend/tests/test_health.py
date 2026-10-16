from httpx import AsyncClient


async def test_health_does_not_require_a_database(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unknown_endpoint_returns_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/missing")

    assert response.status_code == 404
