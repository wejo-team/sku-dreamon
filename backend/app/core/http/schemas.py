"""API의 이름 규칙과 성공·페이지·오류 응답 형식을 정의한다."""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.core.http.types import NonnegativeInt, PageSize, PositiveInt


class RequestDTO(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=False,
        serialize_by_alias=True,
        extra="forbid",
    )


class ResponseDTO(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class Success[T](ResponseDTO):
    data: T


class PageMeta(ResponseDTO):
    page: PositiveInt
    page_size: PageSize
    total: NonnegativeInt
    total_pages: NonnegativeInt


class Page[T](ResponseDTO):
    data: list[T]
    pagination: PageMeta


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
