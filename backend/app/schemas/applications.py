"""지원의 공개 응답과 명시적인 상태 변경 요청을 정의한다."""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from app.core.http.schemas import ResponseDTO, Timestamp, Version
from app.rules.catalogs import RoleCode


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
