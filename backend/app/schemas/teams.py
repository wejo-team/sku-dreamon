"""공개 팀 검색 조건과 관계 정보가 없는 모집글 DTO를 정의한다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.http.schemas import (
    PositiveBigInt,
    PositiveInt,
    RequestDTO,
    ResponseDTO,
    Timestamp,
    Version,
)
from app.rules.catalogs import FieldCode, RoleCode
from app.schemas.contests import ContestSummary, DeadlineInterpretation


class TeamSearch(RequestDTO):
    page: Annotated[int, Field(ge=1, le=9007199254740991)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20
    q: str | None = None
    role_code: RoleCode | None = None
    recruiting_only: bool = False

    @field_validator("q")
    @classmethod
    def validate_search_text(cls, value: str | None) -> str | None:
        if value is not None:
            # PostgreSQL text는 NUL과 UTF-8로 표현할 수 없는 문자를 받지 않는다.
            if "\x00" in value:
                raise ValueError("검색어에 사용할 수 없는 문자가 있습니다.")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ValueError("검색어에 사용할 수 없는 문자가 있습니다.") from error
        return value


class AllTeamSearch(TeamSearch):
    contest_id: UUID | None = None


class TeamSummary(ResponseDTO):
    id: UUID
    version: Version
    contest_id: UUID
    contest_title: str
    name: str
    introduction: str
    field_codes: list[FieldCode]
    role_codes: list[RoleCode]
    capacity: PositiveBigInt
    member_count: PositiveInt
    recruitment_state: Literal["open", "closed"]
    closed_reason: Literal["capacity_reached", "leader_closed"] | None
    recruitment_ends_at: Timestamp
    is_recruiting: bool
    is_demo: bool
    created_at: Timestamp
    recruitment_deadline: DeadlineInterpretation


class TeamDetail(TeamSummary):
    owner_account_id: UUID
    contest: ContestSummary
