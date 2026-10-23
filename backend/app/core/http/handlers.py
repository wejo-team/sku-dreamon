"""애플리케이션·HTTP·검증 오류를 안전한 응답과 추적 ID로 변환한다."""

import logging
from collections.abc import Mapping
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.exceptions import AppError
from app.core.http.schemas import (
    ErrorDetail,
    ErrorResponse,
    ValidationErrorResponse,
    ValidationIssue,
)

logger = logging.getLogger(__name__)

_HTTP_ERRORS = {
    401: ("UNAUTHENTICATED", "로그인이 필요합니다."),
    403: ("FORBIDDEN", "요청을 수행할 권한이 없습니다."),
    404: ("RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다."),
    429: ("RATE_LIMITED", "요청이 많습니다. 잠시 후 다시 시도해 주세요."),
    500: ("INTERNAL_ERROR", "오류가 발생했습니다. 잠시 후 다시 시도해 주세요."),
    503: ("TEMPORARY_UNAVAILABLE", "일시적으로 이용할 수 없습니다."),
}
_HTTP_ERROR_DEFAULT = ("HTTP_ERROR", "요청을 처리할 수 없습니다.")


def _error_response(
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = _record_error(status_code)
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message), request_id=request_id
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=_error_headers(request_id, headers),
    )


def _error_headers(
    request_id: str, headers: Mapping[str, str] | None = None
) -> dict[str, str]:
    response_headers = {
        key: value
        for key, value in (headers or {}).items()
        if key.lower() != "x-request-id"
    }
    response_headers["X-Request-ID"] = request_id
    return response_headers


def _validation_response(
    issues: list[ValidationIssue], headers: Mapping[str, str] | None = None
) -> JSONResponse:
    body = ValidationErrorResponse(detail=issues)
    return JSONResponse(
        status_code=422,
        content=body.model_dump(mode="json"),
        headers=_error_headers(_record_error(422), headers),
    )


def _record_error(status_code: int) -> str:
    request_id = str(uuid4())
    level = logging.ERROR if status_code >= 500 else logging.WARNING
    logger.log(level, "api_error request_id=%s status_code=%s", request_id, status_code)
    return request_id


async def _handle_app_error(request: Request, exception: Exception) -> JSONResponse:
    assert isinstance(exception, AppError)
    return _error_response(
        exception.status_code, exception.code, exception.message, exception.headers
    )


async def _handle_http_error(request: Request, exception: Exception) -> JSONResponse:
    assert isinstance(exception, HTTPException)
    if exception.status_code == 422:
        return _validation_response(
            [
                ValidationIssue(
                    loc=[], msg="입력값을 확인해 주세요.", type="value_error"
                )
            ],
            exception.headers,
        )
    code, message = _HTTP_ERRORS.get(exception.status_code, _HTTP_ERROR_DEFAULT)
    return _error_response(exception.status_code, code, message, exception.headers)


async def _handle_validation_error(
    request: Request, exception: Exception
) -> JSONResponse:
    assert isinstance(exception, RequestValidationError)
    return _validation_response(
        [
            ValidationIssue(
                loc=list(error["loc"]),
                msg="입력값을 확인해 주세요.",
                type=error["type"],
            )
            for error in exception.errors()
        ]
    )


async def _handle_unexpected_error(
    request: Request, exception: Exception
) -> JSONResponse:
    code, message = _HTTP_ERRORS[500]
    return _error_response(500, code, message)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(HTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)


def error_responses(*status_codes: int) -> dict[int | str, dict[str, object]]:
    return {
        status_code: {
            "model": ValidationErrorResponse if status_code == 422 else ErrorResponse
        }
        for status_code in status_codes
    }
