from pydantic import Field

from app.schemas.base import ResponseDTO


class ErrorDetail(ResponseDTO):
    code: str
    message: str


class ErrorResponse(ResponseDTO):
    error: ErrorDetail
    request_id: str


class ValidationIssue(ResponseDTO):
    loc: list[str | int]
    msg: str
    type: str


class ValidationErrorResponse(ResponseDTO):
    detail: list[ValidationIssue] = Field(min_length=1)
