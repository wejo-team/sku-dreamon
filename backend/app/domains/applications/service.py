"""관계에 따른 지원 조회와 지원 시도의 업무 동작을 처리한다."""

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, and_, func, select, true
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.domains.applications.models import Application, ApplicationEvent
from app.domains.applications.schemas import (
    ApplicationResponse,
    ApplicationStatus,
    CancellationResult,
    MyApplication,
)
from app.domains.catalogs.codes import RoleCode
from app.domains.contests.models import Contest, ContestField
from app.domains.notifications.models import Notification
from app.domains.teams.locks import (
    lock_accounts,
    lock_applications,
    lock_contest,
    lock_teams,
)
from app.domains.teams.models import Team, TeamMembership, TeamRecruitmentRole
from app.domains.teams.schemas import build_team_summary


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
    source_event = aliased(ApplicationEvent)
    source_membership = aliased(TeamMembership)
    row = (
        await session.execute(
            select(
                Application,
                Team.leader_account_id,
                ApplicationEvent.reason_code,
                source_event.application_id,
                source_membership.team_id,
            )
            .join(Team, Team.team_id == Application.team_id)
            .outerjoin(
                ApplicationEvent,
                and_(
                    ApplicationEvent.application_id == Application.application_id,
                    ApplicationEvent.application_version == Application.version,
                ),
            )
            .outerjoin(
                source_event,
                source_event.application_event_id == ApplicationEvent.cause_event_id,
            )
            .outerjoin(
                source_membership,
                source_membership.team_membership_id
                == ApplicationEvent.cause_membership_id,
            )
            .where(Application.application_id == application_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None or viewer_id not in (
        row[0].applicant_account_id,
        row[1],
    ):
        raise AppError(404, "APPLICATION_NOT_FOUND", "지원을 찾을 수 없습니다.")
    return application_response(
        row[0],
        viewer_id=viewer_id,
        reason=row[2],
        source_application_id=row[3],
        source_team_id=row[4],
    )


async def list_my_applications(
    session: AsyncSession,
    account_id: UUID,
    *,
    page: int,
    page_size: int,
    status: ApplicationStatus | None,
) -> Page[MyApplication]:
    filters = [Application.applicant_account_id == account_id]
    if status is not None:
        filters.append(Application.status == status.value)
    total = (
        select(func.count().label("total"))
        .select_from(Application)
        .where(*filters)
        .cte("application_total")
    )
    total_pages = sql_cast(func.ceil(total.c.total / page_size), BigInteger)
    meta = select(
        total.c.total,
        total_pages.label("total_pages"),
        func.least(page, func.greatest(total_pages, 1)).label("page"),
    ).cte("application_page")
    page_ids = (
        select(Application.application_id)
        .where(*filters)
        .order_by(Application.submitted_at.desc(), Application.application_id.desc())
        .limit(page_size)
        .offset(select((meta.c.page - 1) * page_size).scalar_subquery())
        .cte("page_applications")
    )
    fields = (
        select(func.array_agg(ContestField.field_code))
        .where(ContestField.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    roles = (
        select(func.array_agg(TeamRecruitmentRole.role_code))
        .where(TeamRecruitmentRole.team_id == Team.team_id)
        .correlate(Team)
        .scalar_subquery()
    )
    member_count = (
        select(func.count())
        .select_from(TeamMembership)
        .where(
            TeamMembership.team_id == Team.team_id, TeamMembership.ended_at.is_(None)
        )
        .correlate(Team)
        .scalar_subquery()
    )
    is_member = (
        select(TeamMembership.team_membership_id)
        .where(
            TeamMembership.team_id == Team.team_id,
            TeamMembership.account_id == account_id,
            TeamMembership.ended_at.is_(None),
        )
        .correlate(Team)
        .exists()
    )
    source_event = aliased(ApplicationEvent)
    source_membership = aliased(TeamMembership)
    # 집계·페이지 보정·지원·소속·원인·팀 요약을 한 SQL 스냅샷에서 읽는다.
    rows = (
        await session.execute(
            select(
                meta.c.total,
                meta.c.total_pages,
                meta.c.page,
                Application,
                Team,
                Contest,
                ApplicationEvent.reason_code,
                source_event.application_id,
                source_membership.team_id,
                fields,
                roles,
                member_count,
                is_member,
            )
            .select_from(meta)
            .outerjoin(page_ids, true())
            .outerjoin(
                Application, Application.application_id == page_ids.c.application_id
            )
            .outerjoin(Team, Team.team_id == Application.team_id)
            .outerjoin(Contest, Contest.contest_id == Team.contest_id)
            .outerjoin(
                ApplicationEvent,
                and_(
                    ApplicationEvent.application_id == Application.application_id,
                    ApplicationEvent.application_version == Application.version,
                ),
            )
            .outerjoin(
                source_event,
                source_event.application_event_id == ApplicationEvent.cause_event_id,
            )
            .outerjoin(
                source_membership,
                source_membership.team_membership_id
                == ApplicationEvent.cause_membership_id,
            )
            .order_by(
                Application.submitted_at.desc(), Application.application_id.desc()
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    now = datetime.now(UTC)
    items = [
        MyApplication(
            application=application_response(
                row[3],
                viewer_id=account_id,
                reason=row[6],
                source_application_id=row[7],
                source_team_id=row[8],
            ),
            team=build_team_summary(
                row[4],
                row[5],
                field_codes=row[9] or [],
                role_codes=row[10] or [],
                member_count=row[11],
                now=now,
            ),
            is_current_member=row[12],
        )
        for row in rows
        if row[3] is not None
    ]
    return Page(
        data=items,
        pagination=PageMeta(
            page=rows[0][2],
            page_size=page_size,
            total=rows[0][0],
            total_pages=rows[0][1],
        ),
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

        membership = await session.scalar(
            select(TeamMembership).where(
                TeamMembership.source_application_id == application_id
            )
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
            if membership is None or membership.ended_at is not None:
                raise RuntimeError("Selected application requires active membership")
            membership.ended_at = now
            membership.end_reason = "application_canceled"
            team.version += 1
            team.updated_at = now
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
        session.add(
            Notification(
                event_id=event.application_event_id,
                recipient_account_id=account_id,
                kind="application_status_changed",
            )
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
