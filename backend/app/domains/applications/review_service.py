"""받은 팀장의 현재 지원자 조회와 명시적 검토 행동을 처리한다."""

from uuid import UUID

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.domains.applications.models import Application, ApplicationEvent
from app.domains.applications.review_schemas import ApplicantResponse, ApplicantSearch
from app.domains.applications.service import application_response
from app.domains.profiles.models import Profile
from app.domains.profiles.queries import build_profile_responses
from app.domains.teams.models import Team, TeamMembership


async def _read_snapshot(session: AsyncSession) -> None:
    if session.in_transaction():
        raise RuntimeError("Applicant reads require a fresh request session")
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


def _applicant_statement() -> Select[tuple[Application, Profile, bool, str]]:
    has_membership = (
        select(TeamMembership.team_membership_id)
        .where(
            TeamMembership.account_id == Application.applicant_account_id,
            TeamMembership.contest_id == Application.contest_id,
            TeamMembership.ended_at.is_(None),
        )
        .exists()
    )
    return (
        select(Application, Profile, has_membership, ApplicationEvent.reason_code)
        .join(Profile, Profile.profile_id == Application.applicant_account_id)
        .outerjoin(
            ApplicationEvent,
            and_(
                ApplicationEvent.application_id == Application.application_id,
                ApplicationEvent.application_version == Application.version,
            ),
        )
    )


async def list_applicants(
    session: AsyncSession, team_id: UUID, account_id: UUID, query: ApplicantSearch
) -> Page[ApplicantResponse]:
    await _read_snapshot(session)
    team = await session.get(Team, team_id)
    if team is None:
        raise AppError(404, "TEAM_NOT_FOUND", "팀을 찾을 수 없습니다.")
    if team.leader_account_id != account_id:
        raise AppError(403, "FORBIDDEN", "팀장만 지원자를 확인할 수 있습니다.")
    conditions = [Application.team_id == team_id]
    if query.status is not None:
        conditions.append(Application.status == query.status.value)
    total = await session.scalar(
        select(func.count()).select_from(Application).where(*conditions)
    )
    assert total is not None
    total_pages = (total + query.page_size - 1) // query.page_size
    page = min(query.page, max(total_pages, 1))
    rows = (
        await session.execute(
            _applicant_statement()
            .where(*conditions)
            .order_by(
                Application.submitted_at.desc(), Application.application_id.desc()
            )
            .offset((page - 1) * query.page_size)
            .limit(query.page_size)
        )
    ).all()
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
    identity = (
        await session.execute(
            select(Application.applicant_account_id, Team.leader_account_id)
            .join(Team, Team.team_id == Application.team_id)
            .where(Application.application_id == application_id)
        )
    ).one_or_none()
    if identity is None or account_id not in identity:
        raise AppError(404, "APPLICATION_NOT_FOUND", "지원을 찾을 수 없습니다.")
    if account_id != identity[1]:
        raise AppError(403, "FORBIDDEN", "팀장만 지원자를 확인할 수 있습니다.")
    application, profile, has_membership, reason = (
        await session.execute(
            _applicant_statement().where(Application.application_id == application_id)
        )
    ).one()
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
