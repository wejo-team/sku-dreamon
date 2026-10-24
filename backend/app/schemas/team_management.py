"""현재 소속의 팀 공간과 팀장 모집 변경에 한정된 전송 계약을 정의한다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.core.http.schemas import (
    NonnegativeInt,
    RequestDTO,
    ResponseDTO,
    Timestamp,
    Version,
)
from app.rules.catalogs import RoleCode
from app.schemas.profiles import ProfileResponse
from app.schemas.teams import TeamDetail, TeamSummary


class WorkspaceSearch(RequestDTO):
    page: Annotated[int, Field(ge=1, le=9007199254740991)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20


class RecruitmentAction(RequestDTO):
    expected_version: Version


class TeamMember(ResponseDTO):
    membership_id: UUID
    account_id: UUID
    real_name: str
    is_demo: bool
    membership_role: Literal["leader", "member"]
    role_code: RoleCode | None
    joined_at: Timestamp
    profile: ProfileResponse | None


class TeamSpace(ResponseDTO):
    team: TeamDetail
    members: list[TeamMember] = Field(min_length=1)
    viewer_role: Literal["leader", "member"]
    pending_application_count: NonnegativeInt | None


class WorkspaceTeam(ResponseDTO):
    team: TeamSummary
    membership_id: UUID
    membership_role: Literal["leader", "member"]
    role_code: RoleCode | None
    pending_application_count: NonnegativeInt | None


class RecruitmentResult(ResponseDTO):
    team: TeamSummary
