"""DB 조회 전에 잘못된 사람 검색어를 HTTP 입력 검증에서 거부한다."""

from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_account
from app.schemas.profiles import PeopleQuery
from app.services import profiles


@pytest.mark.integration
async def test_people_search_rejects_nul_before_service(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def current_account() -> UUID:
        return UUID("00000000-0000-4000-8000-000000000001")

    async def unexpected_lookup(session: AsyncSession, query: PeopleQuery) -> None:
        pytest.fail("잘못된 검색어는 서비스 조회 전에 거부해야 합니다.")

    app.dependency_overrides[get_current_account] = current_account
    monkeypatch.setattr(profiles, "list_people", unexpected_lookup)
    response = await client.get("/api/v1/people", params={"q": "검색\x00어"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "q"]
