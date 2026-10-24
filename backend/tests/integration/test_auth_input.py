"""JSON의 잘못된 Unicode 입력이 비밀번호 해시 전에 거부되는지 검증한다."""

import json

import pytest
from fastapi import FastAPI, Response
from httpx import AsyncClient

from app.schemas.auth import Credentials
from app.security.passwords import hash_password


@pytest.mark.integration
async def test_unpaired_surrogate_password_is_rejected_before_hashing(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    @app.post("/auth-input-probe")
    async def probe(payload: Credentials) -> Response:
        await hash_password(payload.password)
        return Response(status_code=204)

    response = await client.post(
        "/auth-input-probe",
        content=json.dumps({"loginId": "validuser", "password": "a" * 15 + "\ud800"}),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "password"]
    assert "a" * 15 not in response.text
