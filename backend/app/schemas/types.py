import re
from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    PlainSerializer,
    StrictInt,
    StrictStr,
    WithJsonSchema,
)

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
