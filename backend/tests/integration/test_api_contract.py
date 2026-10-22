from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI, Response
from httpx import AsyncClient
from pydantic import field_validator

from app.core.exceptions import AppError
from app.core.http.handlers import error_responses
from app.core.http.schemas import Page, PageMeta, RequestDTO, ResponseDTO, Success
from app.core.http.types import Timestamp, Version

pytestmark = pytest.mark.integration


class ChildRequest(RequestDTO):
    display_name: str
    optional_note: str | None = None


class ProbeRequest(RequestDTO):
    expected_version: Version
    children: list[ChildRequest]
    metadata: dict[str, str]


class ChildResponse(ResponseDTO):
    display_name: str
    optional_note: str | None


class ProbeResponse(ResponseDTO):
    current_version: Version
    created_at: Timestamp
    children: list[ChildResponse]
    metadata: dict[str, str]


class SecretRequest(RequestDTO):
    password: str

    @field_validator("password")
    @classmethod
    def reject_password(cls, value: str) -> str:
        raise ValueError(f"Rejected password: {value}")


@pytest.fixture(autouse=True)
def contract_routes(app: FastAPI) -> None:
    router = APIRouter(prefix="/contract", responses=error_responses(409, 422, 500))

    @router.post("/echo", status_code=201)
    async def echo(payload: ProbeRequest, response: Response) -> Success[ProbeResponse]:
        response.headers["Location"] = "/contract/echo"
        response.set_cookie("test-session", "example", httponly=True)
        return Success(
            data=ProbeResponse(
                current_version=payload.expected_version,
                created_at=datetime(2026, 10, 22, tzinfo=UTC),
                children=[
                    ChildResponse(
                        display_name=child.display_name,
                        optional_note=child.optional_note,
                    )
                    for child in payload.children
                ],
                metadata=payload.metadata,
            )
        )

    @router.get("/page")
    async def page() -> Page[ProbeResponse]:
        return Page(
            data=[], pagination=PageMeta(page=1, page_size=20, total=0, total_pages=0)
        )

    @router.post("/logout", status_code=204)
    async def logout() -> Response:
        response = Response(status_code=204)
        response.delete_cookie("test-session")
        return response

    @router.get("/conflict")
    async def conflict() -> None:
        raise AppError(409, "VERSION_CONFLICT", "정보가 변경되었습니다.")

    @router.get("/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("secret-server-value")

    @router.post("/secret")
    async def secret(payload: SecretRequest) -> None:
        return None

    app.include_router(router)


def request_body() -> dict[str, object]:
    return {
        "expectedVersion": "9223372036854775807",
        "children": [{"displayName": "sample", "optionalNote": None}],
        "metadata": {"user_key": "snake_value"},
    }


async def test_http_serialization_preserves_headers_and_map_keys(
    client: AsyncClient,
) -> None:
    response = await client.post("/contract/echo", json=request_body())

    assert response.status_code == 201
    assert response.headers["location"] == "/contract/echo"
    assert "test-session=example" in response.headers["set-cookie"]
    assert response.json() == {
        "data": {
            "currentVersion": "9223372036854775807",
            "createdAt": "2026-10-22T00:00:00Z",
            "children": [{"displayName": "sample", "optionalNote": None}],
            "metadata": {"user_key": "snake_value"},
        }
    }


@pytest.mark.parametrize("invalid_name", ["snake", "mixed", "nested_optional"])
async def test_http_rejects_request_names_outside_the_contract(
    client: AsyncClient, invalid_name: str
) -> None:
    body = request_body()
    if invalid_name == "snake":
        body["expected_version"] = body.pop("expectedVersion")
    elif invalid_name == "mixed":
        body["expected_version"] = "1"
    else:
        body["children"] = [{"displayName": "sample", "optional_note": "wrong"}]

    response = await client.post("/contract/echo", json=body)

    assert response.status_code == 422
    assert set(response.json()) == {"detail"}
    assert all(
        set(issue) == {"loc", "msg", "type"} for issue in response.json()["detail"]
    )


async def test_validation_error_does_not_echo_validator_input(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/contract/secret", json={"password": "secret-password"}
    )

    assert response.status_code == 422
    assert "secret-password" not in response.text
    issue = response.json()["detail"][0]
    assert issue["loc"] == ["body", "password"]
    assert issue["type"] == "value_error"
    assert set(issue) == {"loc", "msg", "type"}


async def test_business_and_unexpected_errors_use_safe_responses(
    client: AsyncClient,
) -> None:
    conflict = await client.get("/contract/conflict")
    unexpected = await client.get("/contract/unexpected")

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "VERSION_CONFLICT"
    assert unexpected.status_code == 500
    assert unexpected.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-server-value" not in unexpected.text
    for response in (conflict, unexpected):
        assert set(response.json()) == {"error", "requestId"}
        assert response.json()["requestId"] == response.headers["x-request-id"]
        assert UUID(response.json()["requestId"])
    assert conflict.json()["requestId"] != unexpected.json()["requestId"]


async def test_page_and_empty_response_are_not_double_wrapped(
    client: AsyncClient,
) -> None:
    page = await client.get("/contract/page")
    logout = await client.post("/contract/logout")

    assert page.json() == {
        "data": [],
        "pagination": {"page": 1, "pageSize": 20, "total": 0, "totalPages": 0},
    }
    assert logout.status_code == 204
    assert logout.content == b""
    assert "Max-Age=0" in logout.headers["set-cookie"]


async def test_openapi_matches_wire_models_without_a_snapshot(
    client: AsyncClient,
) -> None:
    schema = (await client.get("/openapi.json")).json()
    models = schema["components"]["schemas"]
    request = models["ProbeRequest"]
    response = models["ProbeResponse"]
    assert set(request["properties"]) == {"expectedVersion", "children", "metadata"}
    assert request["additionalProperties"] is False
    assert response["properties"]["currentVersion"]["type"] == "string"
    assert response["properties"]["createdAt"]["format"] == "date-time"
    echo = schema["paths"]["/contract/echo"]["post"]
    success_ref = echo["responses"]["201"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert set(models[success_ref.rsplit("/", 1)[1]]["properties"]) == {"data"}
    assert echo["responses"]["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ValidationErrorResponse"
    }
    assert set(models["ValidationIssue"]["properties"]) == {"loc", "msg", "type"}
    assert (
        "content" not in schema["paths"]["/contract/logout"]["post"]["responses"]["204"]
    )
