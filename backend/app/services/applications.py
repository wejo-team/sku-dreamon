"""지원의 권한·상태·응답 조립과 요청 트랜잭션을 처리한다."""

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.models.applications import Application, ApplicationEvent
from app.repositories import applications as repository
from app.repositories import teams as team_repository
from app.repositories.recruitment_locks import (
    lock_accounts,
    lock_applications,
    lock_contest,
    lock_teams,
)
from app.rules.catalogs import RoleCode
from app.schemas.applications import (
    ApplicationResponse,
    ApplicationStatus,
    CancellationResult,
    MyApplication,
)
from app.services import notifications as notification_service
from app.services import teams as team_service
from app.services.teams import build_team_summary


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


async def list_my_applications(
    session: AsyncSession,
    account_id: UUID,
    *,
    page: int,
    page_size: int,
    status: ApplicationStatus | None,
) -> Page[MyApplication]:
    result = await repository.list_my_application_records(
        session,
        account_id,
        page=page,
        page_size=page_size,
        status=status.value if status is not None else None,
    )
    now = datetime.now(UTC)
    items = [
        MyApplication(
            application=application_response(
                row.application,
                viewer_id=account_id,
                reason=row.reason,
                source_application_id=row.source_application_id,
                source_team_id=row.source_team_id,
            ),
            team=build_team_summary(
                row.team,
                row.contest,
                field_codes=row.field_codes or [],
                role_codes=row.role_codes or [],
                member_count=row.member_count,
                now=now,
            ),
            is_current_member=row.is_current_member,
        )
        for row in result.items
    ]
    return Page(
        data=items,
        pagination=PageMeta(
            page=result.page,
            page_size=page_size,
            total=result.total,
            total_pages=result.total_pages,
        ),
    )


async def cancel_application(
    session: AsyncSession,
    application_id: UUID,
    account_id: UUID,
    expected_version: int,
) -> CancellationResult:
    try:
        identity = await repository.get_application_identity(session, application_id)
        if identity is None or account_id not in (
            identity.applicant_id,
            identity.leader_id,
        ):
            raise AppError(404, "APPLICATION_NOT_FOUND", "지원을 찾을 수 없습니다.")
        if account_id != identity.applicant_id:
            raise AppError(403, "FORBIDDEN", "본인의 지원만 취소할 수 있습니다.")

        await lock_accounts(session, [account_id])
        await lock_contest(session, identity.contest_id)
        team = (await lock_teams(session, [identity.team_id]))[0]
        application = (await lock_applications(session, [application_id]))[0]
        if application.version != expected_version:
            raise AppError(409, "VERSION_CONFLICT", "최신 지원을 확인해 주세요.")
        if application.status not in ("submitted", "reviewing", "selected", "canceled"):
            raise AppError(
                409, "INVALID_APPLICATION_STATE", "현재 상태에서는 취소할 수 없습니다."
            )

        membership = await team_repository.get_application_membership(
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
        await repository.add_event(session, event)
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
