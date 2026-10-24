"""지원의 권한·상태·응답 조립과 요청 트랜잭션을 처리한다."""

from typing import Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.applications import Application
from app.repositories import applications as repository
from app.rules.catalogs import RoleCode
from app.schemas.applications import ApplicationResponse, ApplicationStatus


def application_response(
    application: Application,
    *,
    viewer_id: UUID,
    reason: str | None = None,
    source_application_id: UUID | None = None,
    source_team_id: UUID | None = None,
) -> ApplicationResponse:
    """원인 설명은 공유하되 다른 팀·지원의 식별자는 지원 본인에게만 공개한다."""
    discarded = application.status == "discarded"
    own = application.applicant_account_id == viewer_id
    return ApplicationResponse(
        id=application.application_id,
        version=str(application.version),
        team_id=application.team_id,
        contest_id=application.contest_id,
        applicant_account_id=application.applicant_account_id,
        role_code=RoleCode(application.applied_role_code),
        message=application.message,
        status=ApplicationStatus(application.status),
        discard_reason=cast(
            Literal["selected_elsewhere", "team_created_elsewhere"] | None,
            reason if discarded else None,
        ),
        discarded_by_application_id=source_application_id
        if discarded and own
        else None,
        discarded_by_team_id=source_team_id if discarded and own else None,
        submitted_at=application.submitted_at,
        updated_at=application.status_changed_at,
    )


async def get_application(
    session: AsyncSession, application_id: UUID, viewer_id: UUID
) -> ApplicationResponse:
    row = await repository.get_application_record(session, application_id)
    if row is None or viewer_id not in (
        row.application.applicant_account_id,
        row.leader_id,
    ):
        raise AppError(404, "APPLICATION_NOT_FOUND", "지원을 찾을 수 없습니다.")
    return application_response(
        row.application,
        viewer_id=viewer_id,
        reason=row.reason,
        source_application_id=row.source_application_id,
        source_team_id=row.source_team_id,
    )
