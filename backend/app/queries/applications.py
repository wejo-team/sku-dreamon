"""지원 관계·상태·프로필을 조회하고 읽기 응답을 구성한다."""

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import BigInteger, and_, func, select, true
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.models.applications import Application, ApplicationEvent
from app.models.contests import Contest, ContestField
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole
from app.queries.teams import build_team_summary
from app.rules.catalogs import RoleCode
from app.schemas.applications import (
    ApplicationResponse,
    ApplicationStatus,
    MyApplication,
)


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
