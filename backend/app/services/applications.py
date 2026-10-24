"""지원 업무의 권한·상태·사건과 요청 트랜잭션을 처리한다."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.applications import Application, ApplicationEvent
from app.models.teams import Team
from app.queries.applications import application_response
from app.schemas.applications import CancellationResult
from app.services import notifications as notification_service
from app.services import teams as team_service
from app.services.recruitment_locks import (
    lock_accounts,
    lock_applications,
    lock_contest,
    lock_teams,
)


async def cancel_application(
    session: AsyncSession,
    application_id: UUID,
    account_id: UUID,
    expected_version: int,
) -> CancellationResult:
    try:
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
        if account_id != identity[0]:
            raise AppError(403, "FORBIDDEN", "본인의 지원만 취소할 수 있습니다.")

        await lock_accounts(session, [account_id])
        await lock_contest(session, identity[1])
        team = (await lock_teams(session, [identity[2]]))[0]
        application = (await lock_applications(session, [application_id]))[0]
        if application.version != expected_version:
            raise AppError(409, "VERSION_CONFLICT", "최신 지원을 확인해 주세요.")
        if application.status not in ("submitted", "reviewing", "selected", "canceled"):
            raise AppError(
                409, "INVALID_APPLICATION_STATE", "현재 상태에서는 취소할 수 없습니다."
            )

        membership = await team_service.get_application_membership(
            session, application_id
        )
        if application.status == "canceled":
            result = CancellationResult(
                application=application_response(application, viewer_id=account_id),
                membership_ended=(
                    membership is not None
                    and membership.end_reason == "application_canceled"
                ),
            )
            await session.rollback()
            return result

        previous_status = application.status
        membership_ended = previous_status == "selected"
        # 모든 잠금 대기가 끝난 뒤 실제 서버 시각을 한 번 구한다.
        now = datetime.now(UTC)
        if membership_ended:
            team_service.end_application_membership(team, membership, now=now)
        application.status = "canceled"
        application.status_changed_at = now
        application.version += 1
        event = ApplicationEvent(
            application_event_id=uuid4(),
            application_id=application_id,
            team_id=application.team_id,
            contest_id=application.contest_id,
            applicant_account_id=account_id,
            application_version=application.version,
            from_status=previous_status,
            to_status="canceled",
            actor_account_id=account_id,
            reason_code="canceled",
            occurred_at=now,
        )
        session.add(event)
        await session.flush()
        await notification_service.create_notification(
            session,
            event_id=event.application_event_id,
            recipient_id=account_id,
            kind="application_status_changed",
        )
        result = CancellationResult(
            application=application_response(application, viewer_id=account_id),
            membership_ended=membership_ended,
        )
        await session.commit()
        return result
    except BaseException:
        await session.rollback()
        raise
