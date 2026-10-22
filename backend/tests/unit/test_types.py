from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.types import (
    NonnegativeBigInt,
    NonnegativeInt,
    PageSize,
    PositiveBigInt,
    PositiveInt,
    Timestamp,
    Version,
)


def test_bigint_strings_preserve_boundaries_without_numeric_conversion() -> None:
    positive = TypeAdapter(PositiveBigInt)
    assert positive.validate_python("1") == "1"
    assert positive.validate_python("9223372036854775807") == "9223372036854775807"
    assert TypeAdapter(NonnegativeBigInt).validate_python("0") == "0"
    assert TypeAdapter(Version).dump_json("1") == b'"1"'


@pytest.mark.parametrize(
    "value",
    ["0", "01", "+1", "-1", "1.0", " 1", "1\n", "١", "9223372036854775808", 1, True],
)
def test_positive_bigint_rejects_noncanonical_or_out_of_range_values(
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(PositiveBigInt).validate_python(value)


@pytest.mark.parametrize("value", ["00", "-1", "9223372036854775808", 0])
def test_nonnegative_bigint_requires_canonical_bounded_strings(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(NonnegativeBigInt).validate_python(value)


def test_integer_types_accept_their_boundaries() -> None:
    positive = TypeAdapter(PositiveInt)
    assert positive.validate_python(1) == 1
    assert positive.validate_python(9007199254740991) == 9007199254740991
    assert TypeAdapter(NonnegativeInt).validate_python(0) == 0
    assert TypeAdapter(PageSize).validate_python(1) == 1
    assert TypeAdapter(PageSize).validate_python(100) == 100


@pytest.mark.parametrize("value", [0, 9007199254740992, True, "1", 1.0])
def test_positive_integer_rejects_coercion_and_invalid_bounds(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(PositiveInt).validate_python(value)


def test_nonnegative_integer_rejects_negative_values() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(NonnegativeInt).validate_python(-1)


@pytest.mark.parametrize("value", [0, 101])
def test_page_size_rejects_values_outside_the_page_limit(value: int) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(PageSize).validate_python(value)


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-22T08:00:00Z",
        datetime(2026, 10, 22, 8, tzinfo=UTC),
        datetime(2026, 10, 22, 17, tzinfo=timezone(timedelta(hours=9))),
    ],
)
def test_timestamp_normalizes_aware_values_and_serializes_utc_z(
    value: str | datetime,
) -> None:
    adapter = TypeAdapter(Timestamp)
    parsed = adapter.validate_python(value)

    assert parsed == datetime(2026, 10, 22, 8, tzinfo=UTC)
    assert parsed.tzinfo == UTC
    assert adapter.dump_json(parsed) == b'"2026-10-22T08:00:00Z"'


def test_timestamp_accepts_utc_json_strings_and_preserves_fractional_seconds() -> None:
    adapter = TypeAdapter(Timestamp)
    parsed = adapter.validate_json('"2026-10-22T08:00:00.123456Z"')

    assert parsed.microsecond == 123456
    assert adapter.dump_json(parsed) == b'"2026-10-22T08:00:00.123456Z"'


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 10, 22, 8),
        "2026-10-22T08:00:00",
        "2026-10-22T08:00:00+00:00",
        "2026-10-22T17:00:00+09:00",
        "2026-10-22_08:00:00Z",
        "2026-10-22T08:00Z",
        "2026-10-22T08:00:00,123Z",
        "not-a-dateZ",
        1792656000,
        True,
    ],
)
def test_timestamp_rejects_naive_non_z_or_non_datetime_inputs(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Timestamp).validate_python(value)


def test_timestamp_rejects_numeric_json() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Timestamp).validate_json("1792656000")
