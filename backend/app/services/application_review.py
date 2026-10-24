"""받은 팀장의 조회·검토·선발과 응답·트랜잭션을 처리한다."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import begin_read_snapshot
from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.repositories import applications as repository
from app.schemas.application_review import ApplicantResponse, ApplicantSearch
from app.services.applications import application_response
from app.services.profiles import build_profile_responses


async def _read_snapshot(session: AsyncSession) -> None:
    if session.in_transaction():
        raise RuntimeError("Applicant reads require a fresh request session")
    await begin_read_snapshot(session)


async def list_applicants(
    session: AsyncSession, team_id: UUID, account_id: UUID, query: ApplicantSearch
) -> Page[ApplicantResponse]:
    await _read_snapshot(session)
    team = await repository.get_applicant_team(session, team_id)
    if team is None:
        raise AppError(404, "TEAM_NOT_FOUND", "팀을 찾을 수 없습니다.")
    if team.leader_account_id != account_id:
        raise AppError(403, "FORBIDDEN", "팀장만 지원자를 확인할 수 있습니다.")
    total = await repository.count_applicants(
        session,
        team_id,
        status=query.status.value if query.status is not None else None,
    )
    total_pages = (total + query.page_size - 1) // query.page_size
    page = min(query.page, max(total_pages, 1))
    rows = await repository.list_applicant_records(
        session,
        team_id,
        status=query.status.value if query.status is not None else None,
        offset=(page - 1) * query.page_size,
        limit=query.page_size,
    )
    profiles = await build_profile_responses(session, [row[1] for row in rows])
    return Page(
        data=[
            ApplicantResponse(
                application=application_response(
                    application, viewer_id=account_id, reason=reason
                ),
                profile=profiles[profile.profile_id],
                is_selection_candidate=(
                    application.status in ("submitted", "reviewing")
                    and not has_membership
                ),
            )
            for application, profile, has_membership, reason in rows
        ],
        pagination=PageMeta(
            page=page, page_size=query.page_size, total=total, total_pages=total_pages
        ),
    )


async def get_applicant(
    session: AsyncSession, application_id: UUID, account_id: UUID
) -> ApplicantResponse:
    await _read_snapshot(session)
    identity = await repository.get_application_identity(session, application_id)
    if identity is None or account_id not in (
        identity.applicant_id,
        identity.leader_id,
    ):
        raise AppError(404, "APPLICATION_NOT_FOUND", "지원을 찾을 수 없습니다.")
    if account_id != identity.leader_id:
        raise AppError(403, "FORBIDDEN", "팀장만 지원자를 확인할 수 있습니다.")
    (
        application,
        profile,
        has_membership,
        reason,
    ) = await repository.get_applicant_record(session, application_id)
    profiles = await build_profile_responses(session, [profile])
    return ApplicantResponse(
        application=application_response(
            application, viewer_id=account_id, reason=reason
        ),
        profile=profiles[profile.profile_id],
        is_selection_candidate=(
            application.status in ("submitted", "reviewing") and not has_membership
        ),
    )
