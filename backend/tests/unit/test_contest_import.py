"""운영 공고 입력에서 미확인 자료·잘못된 기간·분류가 거부되는지 확인한다."""

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.contest_import import ContestImport


def payload() -> dict[str, object]:
    return {
        "title": "공식 공고",
        "organizer": "주최 기관",
        "sourceUrl": "https://example.test/contest",
        "eligibilityText": "대학생 참가",
        "audienceCodes": ["student"],
        "fieldCodes": ["design"],
        "capacity": {"kind": "range", "minimumMembers": "1", "maximumMembers": "4"},
        "opening": {"date": "2026-10-01", "time": "09:00", "timeZone": "Asia/Seoul"},
        "closing": {"date": "2026-10-31", "time": None, "timeZone": None},
        "verifiedAt": "2026-10-01T00:00:00Z",
        "description": None,
        "deliverables": None,
        "awards": None,
        "contact": None,
        "posterUrl": None,
    }


def test_confirmed_source_and_date_only_deadline() -> None:
    data = ContestImport.model_validate_json(json.dumps(payload()))
    assert data.opening.resolve().ends_at.isoformat() == "2026-10-01T00:00:00+00:00"
    assert data.closing.resolve().ends_at.isoformat() == "2026-10-31T15:00:00+00:00"
    assert data.closing.resolve().time_assumed


@pytest.mark.parametrize(
    "change",
    [
        {"audienceCodes": ["unknown"]},
        {"audienceCodes": ["student", "unrestricted"]},
        {"fieldCodes": ["design", "design"]},
        {
            "capacity": {
                "kind": "unknown",
                "minimumMembers": None,
                "maximumMembers": None,
            }
        },
        {"opening": {"date": "2026-10-01", "time": None, "timeZone": None}},
        {"opening": {"date": "2026-11-01", "time": "09:00", "timeZone": None}},
        {"closing": {"date": "2026-10-31", "time": "25:00", "timeZone": None}},
        {"sourceUrl": "file:///etc/passwd"},
        {"title": "\u3000\t"},
        {"description": "invalid\u0000text"},
        {"organizer": "invalid\ud800text"},
        {"verified_at": "2026-10-01T00:00:00Z"},
    ],
)
def test_invalid_source_is_rejected(change: dict[str, object]) -> None:
    values = deepcopy(payload())
    values.update(change)
    with pytest.raises(ValidationError):
        ContestImport.model_validate(values)


def test_nested_snake_case_is_not_accepted() -> None:
    values = payload()
    values["capacity"] = {
        "kind": "unlimited",
        "minimum_members": None,
        "maximumMembers": None,
    }
    with pytest.raises(ValidationError):
        ContestImport.model_validate(values)
