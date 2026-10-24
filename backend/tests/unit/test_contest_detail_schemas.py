"""공고 상세 DTO의 십진 문자열·필수 nullable·HTTP(S) URL을 검증한다."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.rules.contests import CapacityKind
from app.schemas.contests import ContestDetail, ParticipationCapacity


def test_large_capacity_is_preserved_as_decimal_strings_in_json() -> None:
    capacity = ParticipationCapacity(
        kind=CapacityKind.RANGE,
        minimum_members="9007199254740993",
        maximum_members="9223372036854775807",
    )

    assert capacity.model_dump(mode="json") == {
        "kind": "range",
        "minimumMembers": "9007199254740993",
        "maximumMembers": "9223372036854775807",
    }


@pytest.mark.parametrize("value", [1, True, "01", "1.0"])
def test_capacity_rejects_noncanonical_or_nonstring_bounds(value: object) -> None:
    with pytest.raises(ValidationError):
        ParticipationCapacity.model_validate(
            {"kind": "range", "minimumMembers": value, "maximumMembers": "2"}
        )


def test_nullable_bounds_must_be_supplied_and_remain_in_json() -> None:
    unknown = ParticipationCapacity(
        kind=CapacityKind.UNKNOWN,
        minimum_members=None,
        maximum_members=None,
    )
    unlimited = ParticipationCapacity(
        kind=CapacityKind.UNLIMITED,
        minimum_members="2",
        maximum_members=None,
    )

    assert unknown.model_dump(mode="json") == {
        "kind": "unknown",
        "minimumMembers": None,
        "maximumMembers": None,
    }
    assert unlimited.model_dump(mode="json")["maximumMembers"] is None
    for omitted in ("minimumMembers", "maximumMembers"):
        payload = {
            "kind": "unknown",
            "minimumMembers": None,
            "maximumMembers": None,
        }
        del payload[omitted]
        with pytest.raises(ValidationError):
            ParticipationCapacity.model_validate(payload)


@pytest.mark.parametrize("field", ["source_url", "poster_url"])
@pytest.mark.parametrize("value", ["ftp://example.test/file", "not a URL"])
def test_public_urls_keep_the_http_and_https_format_requirement(
    field: str, value: str
) -> None:
    annotation = ContestDetail.model_fields[field].annotation
    assert annotation is not None
    adapter = TypeAdapter(annotation)
    with pytest.raises(ValidationError):
        adapter.validate_python(value)
