"""카탈로그 공개 HTTP 응답과 OpenAPI 전송 계약을 검사한다."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_catalogs_are_public_and_use_the_success_envelope(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/catalogs")
    assert response.status_code == 200
    assert set(response.json()) == {"data"}
    assert response.json()["data"]["roles"][0] == {
        "code": "planning",
        "displayName": "기획",
        "isSelectable": True,
        "sortOrder": 0,
    }
    schema = (await client.get("/openapi.json")).json()
    operation = schema["paths"]["/api/v1/catalogs"]["get"]
    assert "security" not in operation
    assert set(operation["responses"]) == {"200", "500", "503"}
