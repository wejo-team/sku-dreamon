"""받은 팀장의 조회·검토·선발과 응답·트랜잭션을 처리한다."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import begin_read_snapshot
from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.models.applications import Application, ApplicationEvent
from app.models.teams import Team
from app.repositories import applications as repository
from app.repositories.recruitment_locks import (
    lock_accounts,
    lock_applications,
    lock_contest,
    lock_teams,
)
from app.schemas.application_review import ApplicantResponse, ApplicantSearch
from app.schemas.applications import ApplicationResponse
from app.services import notifications as notification_service
from app.services.applications import application_response
from app.services.profiles import build_profile_responses


async def _read_snapshot(session: AsyncSession) -> None:
    if session.in_transaction():
        raise RuntimeError("Applicant reads require a fresh request session")
    await begin_read_snapshot(session)


async def _leader_identity(
    session: AsyncSession, application_id: UUID, account_id: UUID
) -> tuple[UUID, UUID, UUID]:
    identity = await repository.get_application_identity(session, application_id)
    if identity is None or account_id not in (
        identity.applicant_id,
        identity.leader_id,
    ):
        raise AppError(404, "APPLICATION_NOT_FOUND", "지원을 찾을 수 없습니다.")
    if account_id != identity.leader_id:
        raise AppError(403, "FORBIDDEN", "지원받은 팀장만 처리할 수 있습니다.")
    return identity.applicant_id, identity.contest_id, identity.team_id


def _check_action(
    application: Application, team: Team, account_id: UUID, expected_version: int
) -> None:
    # 잠금 전 읽은 권한과 버전을 실제 처리 직전에 다시 확인한다.
    if team.leader_account_id != account_id:
        raise AppError(403, "FORBIDDEN", "지원받은 팀장만 처리할 수 있습니다.")
    if application.version != expected_version:
        raise AppError(409, "VERSION_CONFLICT", "최신 지원을 확인해 주세요.")


async def _record_change(
    session: AsyncSession,
    application: Application,
    *,
    status: str,
    actor_id: UUID | None,
    reason: str,
    now: datetime,
    cause_event_id: UUID | None = None,
) -> ApplicationEvent:
    previous = application.status
    application.status = status
    application.version += 1
    application.status_changed_at = now
    event = ApplicationEvent(
        application_event_id=uuid4(),
        application_id=application.application_id,
        team_id=application.team_id,
        contest_id=application.contest_id,
        applicant_account_id=application.applicant_account_id,
        application_version=application.version,
        from_status=previous,
        to_status=status,
        actor_account_id=actor_id,
        reason_code=reason,
        occurred_at=now,
        cause_event_id=cause_event_id,
    )
    await repository.add_event(session, event)
    await notification_service.create_notification(
        session,
        event_id=event.application_event_id,
        recipient_id=application.applicant_account_id,
        kind="application_status_changed",
    )
    return event


async def change_review_status(
    session: AsyncSession,
    application_id: UUID,
    account_id: UUID,
    expected_version: int,
    target: Literal["reviewing", "rejected"],
) -> ApplicationResponse:
    """검토 시작·미선발을 명시적으로 처리하며 동일 상태는 현재 버전에서만 성공한다."""
    try:
        applicant_id, contest_id, team_id = await _leader_identity(
            session, application_id, account_id
        )
        await lock_accounts(session, [applicant_id])
        await lock_contest(session, contest_id)
        team = (await lock_teams(session, [team_id]))[0]
        application = (await lock_applications(session, [application_id]))[0]
        _check_action(application, team, account_id, expected_version)
        if application.status == target:
            result = application_response(application, viewer_id=account_id)
            await session.rollback()
            return result
        permitted = (
            ("submitted",) if target == "reviewing" else ("submitted", "reviewing")
        )
        if application.status not in permitted:
            raise AppError(
                409,
                "INVALID_APPLICATION_STATE",
                "현재 지원 상태에서는 처리할 수 없습니다.",
            )
        await _record_change(
            session,
            application,
            status=target,
            actor_id=account_id,
            reason="reviewing_started" if target == "reviewing" else "rejected",
            now=datetime.now(UTC),
        )
        result = application_response(application, viewer_id=account_id)
        await session.commit()
        return result
    except BaseException:
        await session.rollback()
        raise


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
