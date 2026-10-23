"""공통 선택지의 공개 응답 DTO를 같은 서버 코드 정의에서 구성한다."""

from typing import Annotated

from pydantic import Field, HttpUrl

from app.core.http.schemas import PositiveBigInt, ResponseDTO
from app.domains.catalogs.codes import (
    AcademicStatusCode,
    CatalogCode,
    FieldCode,
    GradeCode,
    ProfileImageCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
)


class CatalogItem(ResponseDTO):
    code: Annotated[str, Field(min_length=1, max_length=64)]
    display_name: str
    is_selectable: bool
    sort_order: Annotated[int, Field(ge=-2147483648, le=2147483647)]


class AvatarPreset(CatalogItem):
    asset_url: HttpUrl


class Catalogs(ResponseDTO):
    fields: list[CatalogItem]
    roles: list[CatalogItem]
    skills: list[CatalogItem]
    academic_statuses: list[CatalogItem]
    grades: list[CatalogItem]
    weekly_availability_ranges: list[CatalogItem]
    avatar_presets: list[AvatarPreset]


class AcademicUnitResponse(ResponseDTO):
    id: PositiveBigInt
    name: Annotated[str, Field(min_length=1, max_length=100)]
    parent_id: PositiveBigInt | None
    is_selectable: bool


def _items(enum_type: type[CatalogCode]) -> list[CatalogItem]:
    return [
        CatalogItem(
            code=item.value,
            display_name=item.display_name,
            is_selectable=item.is_selectable,
            sort_order=item.sort_order,
        )
        for item in sorted(enum_type, key=lambda item: (item.sort_order, item.value))
    ]


def build_catalogs() -> Catalogs:
    return Catalogs(
        fields=_items(FieldCode),
        roles=_items(RoleCode),
        skills=_items(SkillCode),
        academic_statuses=_items(AcademicStatusCode),
        grades=_items(GradeCode),
        weekly_availability_ranges=_items(WeeklyAvailabilityCode),
        avatar_presets=[
            AvatarPreset(
                code=item.value,
                display_name=item.display_name,
                is_selectable=item.is_selectable,
                sort_order=item.sort_order,
                asset_url=HttpUrl(item.asset_url),
            )
            for item in sorted(
                ProfileImageCode, key=lambda item: (item.sort_order, item.value)
            )
        ],
    )
