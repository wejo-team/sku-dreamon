"""프로필 입력의 NFC 길이·경험 정규화·전체 필드 계약을 검증한다."""

import pytest
from pydantic import ValidationError

from app.schemas.profile_write import ProfileWrite


def payload() -> dict[str, object]:
    return dict(
        expectedVersion="0",
        realName="  가  ",
        profileImageCode=None,
        academicStatusCode=None,
        gradeCode=None,
        weeklyAvailabilityCode=None,
        academicUnitId=None,
        experienceState="provided",
        experienceBody="  ",
        introduction=None,
        fieldCodes=["design"],
        roleCodes=["development"],
        skillCodes=[],
        portfolio=None,
    )


def test_normalized_profile_and_blank_experience() -> None:
    data = ProfileWrite.model_validate(payload())
    assert data.real_name == "가"
    assert data.experience_state == "unspecified" and data.experience_body is None


@pytest.mark.parametrize(
    "change",
    [
        {"realName": "가" * 51},
        {"introduction": "a" * 301},
        {"realName": "\x00"},
        {"realName": "\ud800"},
        {"realName": "   "},
        {"roleCodes": ["development", "development"]},
        {"fieldCodes": []},
        {"isPublic": True},
        {"real_name": "다른 이름"},
        {"portfolio": {"url": "file:///local", "title": None}},
    ],
)
def test_invalid_profile(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProfileWrite.model_validate(payload() | change)
