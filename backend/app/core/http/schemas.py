"""API 공통 타입의 검증·직렬화와 DTO·성공·페이지·오류 응답 형식을 정의한다."""

import re
from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictInt,
    StrictStr,
    WithJsonSchema,
)
from pydantic.alias_generators import to_camel

_MAX_BIGINT = 9223372036854775807
_MAX_SAFE_INTEGER = 9007199254740991
_TIMESTAMP_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$"
)


def _check_bigint_limit(value: str) -> str:
    if int(value) > _MAX_BIGINT:
        raise ValueError("Must not exceed the signed 64-bit integer limit")
    return value


PositiveBigInt = Annotated[
    StrictStr,
    Field(min_length=1, max_length=19, pattern=r"^[1-9][0-9]*$"),
    AfterValidator(_check_bigint_limit),
]
NonnegativeBigInt = Annotated[
    StrictStr,
    Field(min_length=1, max_length=19, pattern=r"^(0|[1-9][0-9]*)$"),
    AfterValidator(_check_bigint_limit),
]
Version = PositiveBigInt

PositiveInt = Annotated[StrictInt, Field(ge=1, le=_MAX_SAFE_INTEGER)]
NonnegativeInt = Annotated[StrictInt, Field(ge=0, le=_MAX_SAFE_INTEGER)]
PageSize = Annotated[StrictInt, Field(ge=1, le=100)]


def _require_timestamp(value: object) -> datetime | str:
    if isinstance(value, datetime):
        if value.utcoffset() is not None:
            return value
    elif isinstance(value, str) and re.fullmatch(_TIMESTAMP_PATTERN, value):
        return value
    raise ValueError("Must be an aware datetime or a UTC timestamp ending in Z")


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _serialize_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


Timestamp = Annotated[
    datetime,
    BeforeValidator(_require_timestamp),
    AfterValidator(_to_utc),
    PlainSerializer(_serialize_timestamp, return_type=str, when_used="json"),
    WithJsonSchema(
        {"type": "string", "format": "date-time", "pattern": _TIMESTAMP_PATTERN}
    ),
]


class RequestDTO(BaseModel):
    """camelCase 필드로 받는 공통 API 요청 모델."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=False,
        serialize_by_alias=True,
        extra="forbid",
    )


class ResponseDTO(BaseModel):
    """camelCase 필드로 직렬화하는 공통 API 응답 모델."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class Success[T](ResponseDTO):
    """성공한 요청의 결과를 담는 응답."""

    data: T = Field(
        description=("요청 처리 결과. 구체적인 구조는 해당 API의 응답 모델을 따릅니다.")
    )


class PageMeta(ResponseDTO):
    """현재 목록과 같은 조회 조건으로 계산한 페이지 정보."""

    page: PositiveInt = Field(
        description=(
            "현재 페이지 번호. 1부터 시작하며 조회 결과에 맞게 보정된 값입니다."
        )
    )
    page_size: PageSize = Field(description="페이지당 최대 항목 수.")
    total: NonnegativeInt = Field(description="현재 권한과 필터에 맞는 전체 항목 수.")
    total_pages: NonnegativeInt = Field(
        description=(
            "현재 페이지 크기를 기준으로 계산한 전체 페이지 수. 결과가 없으면 0입니다."
        )
    )


class Page[T](ResponseDTO):
    """현재 페이지의 항목과 조회 조건에 맞는 페이지 정보."""

    data: list[T] = Field(
        description="현재 페이지의 항목 목록. 결과가 없으면 빈 배열입니다."
    )
    pagination: PageMeta = Field(
        description="현재 목록의 권한·필터·읽기 시점에 맞는 페이지 정보."
    )


class ErrorDetail(ResponseDTO):
    """요청 실패를 식별하는 오류 코드와 사용자 안내."""

    code: str = Field(description="클라이언트가 오류 종류를 구분하는 코드.")
    message: str = Field(description="사용자에게 제공하는 오류 안내 메시지.")


class ErrorResponse(ResponseDTO):
    """업무 또는 서버 오류와 요청 추적 정보를 담는 응답."""

    error: ErrorDetail = Field(description="오류 코드와 사용자 안내 메시지.")
    request_id: str = Field(
        description=(
            "오류 요청을 추적하는 식별자. X-Request-ID 응답 헤더와 같은 값입니다."
        )
    )


class ValidationIssue(ResponseDTO):
    """요청 값 검증에 실패한 위치와 안전한 오류 안내."""

    loc: list[str | int] = Field(
        description=(
            "오류 위치의 경로. 입력 영역·필드명·배열 위치 등을 순서대로 나타냅니다."
        )
    )
    msg: str = Field(description="입력 원문을 포함하지 않는 검증 오류 안내.")
    type: str = Field(description="검증 실패의 종류를 식별하는 코드.")


class ValidationErrorResponse(ResponseDTO):
    """요청 입력 검증에 실패했을 때 반환하는 오류 목록."""

    detail: list[ValidationIssue] = Field(
        min_length=1, description="입력 검증 오류 목록. 하나 이상의 오류를 포함합니다."
    )
