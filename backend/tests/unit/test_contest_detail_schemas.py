"""참가 인원 DTO의 십진 문자열과 필수 nullable 필드 전송을 검증한다."""

import pytest
from pydantic import ValidationError

from app.domains.contests.rules import CapacityKind
from app.domains.contests.schemas import ParticipationCapacity


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
