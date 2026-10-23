"""읽기 전용 프로필 DTO와 공개 사람 탐색의 query 계약을 정의한다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field

from app.core.http.schemas import (
    PositiveBigInt,
    RequestDTO,
    ResponseDTO,
    Timestamp,
    Version,
)
from app.domains.catalogs.codes import (
    AcademicStatusCode,
    FieldCode,
    GradeCode,
    ProfileImageCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
)


class PortfolioResponse(ResponseDTO):
    url: AnyHttpUrl
    title: str | None


class PersonSummary(ResponseDTO):
    account_id: UUID
    real_name: str
    is_demo: bool
    profile_image_code: ProfileImageCode | None
    introduction: str | None
    field_codes: Annotated[list[FieldCode], Field(min_length=1, max_length=3)]
    role_codes: Annotated[list[RoleCode], Field(min_length=1, max_length=2)]
    skill_codes: list[SkillCode]


class ProfileResponse(PersonSummary):
    version: Version
    is_public: bool
    updated_at: Timestamp
    academic_status_code: AcademicStatusCode | None
    grade_code: GradeCode | None
    weekly_availability_code: WeeklyAvailabilityCode | None
    academic_unit_id: PositiveBigInt | None
    experience_state: Literal["unspecified", "none", "provided"]
    experience_body: str | None
    portfolio: PortfolioResponse | None


class PeopleQuery(RequestDTO):
    q: str | None = None
    field_code: FieldCode | None = None
    role_code: RoleCode | None = None
    page: Annotated[int, Field(ge=1, le=9007199254740991)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20
