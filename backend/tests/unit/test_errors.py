import json
from collections.abc import Awaitable, Callable
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.core.exceptions import AppError
from app.core.http.handlers import error_responses, register_error_handlers
from app.core.http.schemas import ErrorResponse, ValidationErrorResponse


async def handle_error(exception: Exception) -> Response:
    app = FastAPI()
    register_error_handlers(app)
    handler = cast(
        Callable[[Request, Exception], Awaitable[Response]],
        app.exception_handlers[type(exception)]
        if type(exception) in app.exception_handlers
        else app.exception_handlers[Exception],
    )
    return await handler(Request({"type": "http"}), exception)


async def test_app_error_preserves_contract_headers_and_log_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = await handle_error(
        AppError(
            status_code=409,
            code="VERSION_CONFLICT",
            message="최신 정보를 확인해 주세요.",
            headers={"Retry-After": "2"},
        )
    )
    body = json.loads(bytes(response.body))

    assert response.status_code == 409
    assert body["error"] == {
        "code": "VERSION_CONFLICT",
        "message": "최신 정보를 확인해 주세요.",
    }
    assert UUID(body["requestId"])
    assert response.headers["x-request-id"] == body["requestId"]
    assert response.headers["retry-after"] == "2"
    assert body["requestId"] in caplog.text


def test_app_error_rejects_request_validation_status() -> None:
    with pytest.raises(ValueError, match="422.*request validation"):
        AppError(422, "INVALID_PROFILE", "입력값을 확인해 주세요.")


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (401, "UNAUTHENTICATED"),
        (403, "FORBIDDEN"),
        (404, "RESOURCE_NOT_FOUND"),
        (429, "RATE_LIMITED"),
        (500, "INTERNAL_ERROR"),
        (503, "TEMPORARY_UNAVAILABLE"),
        (418, "HTTP_ERROR"),
    ],
)
async def test_http_error_uses_safe_message_and_preserves_status_and_headers(
    status_code: int, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "password-from-http-detail"
    response = await handle_error(
        HTTPException(
            status_code=status_code,
            detail=secret,
            headers={"Retry-After": "5"},
        )
    )

    assert response.status_code == status_code
    assert json.loads(bytes(response.body))["error"]["code"] == code
    assert response.headers["retry-after"] == "5"
    assert secret not in bytes(response.body).decode()
    assert secret not in caplog.text


async def test_http_422_uses_validation_contract_and_preserves_headers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "password-from-http-422"
    response = await handle_error(
        HTTPException(
            status_code=422,
            detail=secret,
            headers={"Retry-After": "3", "x-request-id": "untrusted-id"},
        )
    )

    assert response.status_code == 422
    assert json.loads(bytes(response.body)) == {
        "detail": [{"loc": [], "msg": "입력값을 확인해 주세요.", "type": "value_error"}]
    }
    assert response.headers["retry-after"] == "3"
    assert UUID(response.headers["x-request-id"])
    assert response.headers["x-request-id"] in caplog.text
    assert secret not in bytes(response.body).decode()
    assert secret not in caplog.text


async def test_validation_error_removes_input_context_and_unsafe_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "password-from-validator"
    response = await handle_error(
        RequestValidationError(
            [
                {
                    "loc": ("body", "credentials", 0, "password"),
                    "msg": f"Invalid password: {secret}",
                    "type": "value_error",
                    "input": secret,
                    "ctx": {"error": ValueError(secret)},
                    "url": "https://errors.example/validation",
                }
            ],
            body={"password": secret},
        )
    )
    body = json.loads(bytes(response.body))

    assert response.status_code == 422
    assert body == {
        "detail": [
            {
                "loc": ["body", "credentials", 0, "password"],
                "msg": "입력값을 확인해 주세요.",
                "type": "value_error",
            }
        ]
    }
    assert secret not in bytes(response.body).decode()
    assert secret not in caplog.text
    assert UUID(response.headers["x-request-id"])
    assert response.headers["x-request-id"] in caplog.text


async def test_unexpected_error_does_not_expose_exception_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "database-password-in-exception"
    response = await handle_error(RuntimeError(secret))
    body = json.loads(bytes(response.body))

    assert response.status_code == 500
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["requestId"] == response.headers["x-request-id"]
    assert body["requestId"] in caplog.text
    assert secret not in bytes(response.body).decode()
    assert secret not in caplog.text


def test_openapi_error_definitions_use_the_matching_response_models() -> None:
    responses = error_responses(409, 422, 503)

    assert set(responses) == {409, 422, 503}
    assert responses[409]["model"] is ErrorResponse
    assert responses[422]["model"] is ValidationErrorResponse
    assert responses[503]["model"] is ErrorResponse
