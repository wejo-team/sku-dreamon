"""모델에 전달하는 코드 사전이 실제 카탈로그·프로필 계약과 일치하는지 검사한다."""

from typing import get_args

import pytest

from app.agents.prompts import AGENT_PROMPT
from app.rules.catalogs import (
    CatalogCode,
    FieldCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
)
from app.schemas.profiles import ProfileResponse


@pytest.mark.parametrize(
    ("label", "catalog"),
    [
        ("분야 field_codes", FieldCode),
        ("역할 role_codes 및 지원 역할 role", RoleCode),
        ("역량 skill_codes", SkillCode),
        ("주당 시간 weekly_availability_code", WeeklyAvailabilityCode),
    ],
)
def test_model_facts_dictionary_matches_catalog(
    label: str, catalog: type[CatalogCode]
) -> None:
    meanings = next(
        line.removeprefix(f"- {label}: ")
        for line in AGENT_PROMPT.splitlines()
        if line.startswith(f"- {label}: ")
    )
    assert dict(item.split("=", 1) for item in meanings.split(", ")) == {
        item.value: item.display_name for item in catalog
    }


def test_experience_dictionary_distinguishes_missing_and_none() -> None:
    expected = {"unspecified": "미입력", "none": "경험 없음", "provided": "본문 입력"}
    actual_codes = get_args(ProfileResponse.model_fields["experience_state"].annotation)
    assert set(actual_codes) == set(expected)
    meanings = next(
        line.removeprefix("- 경험 입력 experience_state: ")
        for line in AGENT_PROMPT.splitlines()
        if line.startswith("- 경험 입력 experience_state: ")
    )
    assert dict(item.split("=", 1) for item in meanings.split(", ")) == expected
