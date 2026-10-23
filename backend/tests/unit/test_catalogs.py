"""명세의 공통 선택지와 저장 코드의 불변·종류별 검증 계약을 확인한다."""

import pytest

from app.core.exceptions import AppError
from app.domains.catalogs.codes import (
    CatalogCode,
    FieldCode,
    ProfileImageCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
    validate_catalog_selection,
)
from app.domains.catalogs.schemas import build_catalogs


def test_catalogs_provide_seven_ordered_lists_with_stable_codes() -> None:
    payload = build_catalogs().model_dump(mode="json")
    assert set(payload) == {
        "fields",
        "roles",
        "skills",
        "academicStatuses",
        "grades",
        "weeklyAvailabilityRanges",
        "avatarPresets",
    }
    assert [len(items) for items in payload.values()] == [10, 6, 13, 3, 5, 4, 5]
    for items in payload.values():
        assert items == sorted(
            items, key=lambda item: (item["sortOrder"], item["code"])
        )
        assert len({item["code"] for item in items}) == len(items)
        assert all(item["isSelectable"] for item in items)
        assert not any(item["displayName"] == "기타" for item in items)
    assert payload["roles"][0]["code"] == "planning"
    assert payload["roles"][4]["displayName"] == "자료조사"
    assert all(
        item["assetUrl"].startswith("https://") for item in payload["avatarPresets"]
    )


def test_selection_validation_is_specific_to_the_catalog_kind() -> None:
    assert validate_catalog_selection(FieldCode, "design") is FieldCode.DESIGN
    assert validate_catalog_selection(RoleCode, "design") is RoleCode.DESIGN
    assert validate_catalog_selection(SkillCode, None) is None
    assert len(WeeklyAvailabilityCode) == 4
    assert ProfileImageCode.SKON.value == "skon"
    with pytest.raises(AppError) as raised:
        validate_catalog_selection(RoleCode, "programming")
    assert raised.value.status_code == 409
    assert raised.value.code == "INVALID_CATALOG_SELECTION"


def test_display_names_are_not_accepted_as_storage_codes() -> None:
    with pytest.raises(AppError):
        validate_catalog_selection(FieldCode, "IT·기술")


def test_inactive_codes_can_only_be_kept_as_the_previous_selection() -> None:
    class RetiredCode(CatalogCode):
        OLD = "old", "이전 선택", 0, False

    with pytest.raises(AppError):
        validate_catalog_selection(RetiredCode, "old")
    assert validate_catalog_selection(RetiredCode, "old", "old") is RetiredCode.OLD
