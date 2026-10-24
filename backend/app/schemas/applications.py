"""지원의 공개 응답과 명시적인 상태 변경 요청을 정의한다."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.core.http.schemas import RequestDTO, ResponseDTO, Timestamp, Version
from app.rules.catalogs import RoleCode
from app.schemas.teams import TeamSummary


class ApplicationStatus(StrEnum):
    SUBMITTED = "submitted"
    REVIEWING = "reviewing"
    SELECTED = "selected"
    REJECTED = "rejected"
    CANCELED = "canceled"
    DISCARDED = "discarded"


class ApplicationResponse(ResponseDTO):
    id: UUID
    version: Version
    team_id: UUID
    contest_id: UUID
    applicant_account_id: UUID
    role_code: RoleCode
    message: str | None
    status: ApplicationStatus
    discard_reason: Literal["selected_elsewhere", "team_created_elsewhere"] | None
    discarded_by_application_id: UUID | None
    discarded_by_team_id: UUID | None
    submitted_at: Timestamp
    updated_at: Timestamp


class VersionedAction(RequestDTO):
    expected_version: Version


class CancellationResult(ResponseDTO):
    application: ApplicationResponse
    membership_ended: bool


class MyApplication(ResponseDTO):
    application: ApplicationResponse
    team: TeamSummary
    is_current_member: bool


class ApplicationSearch(RequestDTO):
    page: Annotated[int, Field(ge=1, le=9007199254740991)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20
    status: ApplicationStatus | None = None
