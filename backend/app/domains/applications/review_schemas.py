"""받은 지원의 팀장 검토용 조회·처리 결과를 정의한다."""

from typing import Annotated
from uuid import UUID

from pydantic import Field

from app.core.http.schemas import RequestDTO, ResponseDTO
from app.domains.applications.schemas import ApplicationResponse, ApplicationStatus
from app.domains.profiles.schemas import ProfileResponse
from app.domains.teams.schemas import TeamSummary


class ApplicantSearch(RequestDTO):
    page: Annotated[int, Field(ge=1, le=9007199254740991)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20
    status: ApplicationStatus | None = None


class ApplicantResponse(ResponseDTO):
    application: ApplicationResponse
    profile: ProfileResponse
    is_selection_candidate: bool


class SelectionResult(ResponseDTO):
    application: ApplicationResponse
    team: TeamSummary
    membership_id: UUID
