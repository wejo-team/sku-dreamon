"""받은 팀장의 현재 지원자 조회와 명시적 검토 행동을 처리한다."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import Page
from app.models.applications import Application, ApplicationEvent
from app.models.teams import Team
from app.queries import applications as application_queries
from app.queries.applications import application_response
from app.schemas.application_review import ApplicantResponse, ApplicantSearch
from app.schemas.applications import ApplicationResponse
from app.services import notifications as notification_service
from app.services.recruitment_locks import (
    lock_accounts,
    lock_applications,
    lock_contest,
    lock_teams,
)


async def _read_snapshot(session: AsyncSession) -> None:
    if session.in_transaction():
        raise RuntimeError("Applicant reads require a fresh request session")
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


async def _leader_identity(
    session: AsyncSession, application_id: UUID, account_id: UUID
) -> tuple[UUID, UUID, UUID]:
    identity = (
        await session.execute(
            select(
                Application.applicant_account_id,
                Application.contest_id,
                Application.team_id,
                Team.leader_account_id,
            )
            .join(Team, Team.team_id == Application.team_id)
            .where(Application.application_id == application_id)
        )
    ).one_or_none()
    if identity is None or account_id not in (identity[0], identity[3]):
        raise AppError(404, "APPLICATION_NOT_FOUND", "지원을 찾을 수 없습니다.")
    if account_id != identity[3]:
        raise AppError(403, "FORBIDDEN", "지원받은 팀장만 처리할 수 있습니다.")
    return identity[0], identity[1], identity[2]


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
    session.add(event)
    await session.flush()
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
    return await application_queries.list_applicants(
        session, team_id, account_id, query
    )


async def get_applicant(
    session: AsyncSession, application_id: UUID, account_id: UUID
) -> ApplicantResponse:
    await _read_snapshot(session)
    return await application_queries.get_applicant(session, application_id, account_id)
