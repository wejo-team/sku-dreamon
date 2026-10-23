"""카탈로그 공개 HTTP 응답과 OpenAPI 전송 계약을 검사한다."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.http.handlers import register_error_handlers
from app.domains.catalogs.router import router

pytestmark = pytest.mark.integration


async def test_catalogs_are_public_and_use_the_success_envelope() -> None:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
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
