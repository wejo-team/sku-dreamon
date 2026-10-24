"""공통 선택지와 학사 소속의 공개 응답 DTO를 정의한다."""

from typing import Annotated

from pydantic import Field, HttpUrl

from app.core.http.schemas import PositiveBigInt, ResponseDTO


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
