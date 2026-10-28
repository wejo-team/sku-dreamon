"""지원 조회와 사건 저장을 수행하고 내부 ORM 결과만 반환한다."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import BigInteger, Select, and_, func, or_, select, true
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.applications import Application, ApplicationEvent
from app.models.contests import Contest, ContestField
from app.models.profiles import Profile
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole


class ApplicationDetailRecord(NamedTuple):
    application: Application
    leader_id: UUID
    reason: str | None
    source_application_id: UUID | None
    source_team_id: UUID | None


async def get_application_record(
    session: AsyncSession, application_id: UUID
) -> ApplicationDetailRecord | None:
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
    return ApplicationDetailRecord(*row) if row is not None else None


class MyApplicationRecord(NamedTuple):
    application: Application
    team: Team
    contest: Contest
    reason: str | None
    source_application_id: UUID | None
    source_team_id: UUID | None
    field_codes: list[str]
    role_codes: list[str]
    member_count: int
    is_current_member: bool


class MyApplicationsPage(NamedTuple):
    total: int
    total_pages: int
    page: int
    items: list[MyApplicationRecord]


async def list_my_application_records(
    session: AsyncSession,
    account_id: UUID,
    *,
    page: int,
    page_size: int,
    status: str | None,
) -> MyApplicationsPage:
    filters = [Application.applicant_account_id == account_id]
    if status is not None:
        filters.append(Application.status == status)
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
    return MyApplicationsPage(
        total=rows[0][0],
        total_pages=rows[0][1],
        page=rows[0][2],
        items=[
            MyApplicationRecord(
                application=row[3],
                team=row[4],
                contest=row[5],
                reason=row[6],
                source_application_id=row[7],
                source_team_id=row[8],
                field_codes=list(row[9] or []),
                role_codes=list(row[10] or []),
                member_count=row[11],
                is_current_member=row[12],
            )
            for row in rows
            if row[3] is not None
        ],
    )


class ApplicationIdentity(NamedTuple):
    applicant_id: UUID
    contest_id: UUID
    team_id: UUID
    leader_id: UUID


async def get_application_identity(
    session: AsyncSession, application_id: UUID
) -> ApplicationIdentity | None:
    row = (
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
    return ApplicationIdentity(*row) if row is not None else None


async def add_event(session: AsyncSession, event: ApplicationEvent) -> None:
    """서비스가 확정한 사건과 같은 세션의 변경을 기존 시점에 flush한다."""
    session.add(event)
    await session.flush()


class ApplicantRecord(NamedTuple):
    application: Application
    profile: Profile
    has_membership: bool
    reason: str | None


async def get_applicant_team(session: AsyncSession, team_id: UUID) -> Team | None:
    return await session.get(Team, team_id)


async def count_applicants(
    session: AsyncSession,
    team_id: UUID,
    *,
    status: str | None,
    pending_only: bool = False,
) -> int:
    conditions = [Application.team_id == team_id]
    if status is not None:
        conditions.append(Application.status == status)
    if pending_only:
        conditions.append(Application.status.in_(("submitted", "reviewing")))
    count = await session.scalar(
        select(func.count()).select_from(Application).where(*conditions)
    )
    assert count is not None
    return count


async def list_applicant_records(
    session: AsyncSession,
    team_id: UUID,
    *,
    status: str | None,
    offset: int,
    limit: int,
    pending_only: bool = False,
) -> list[ApplicantRecord]:
    conditions = [Application.team_id == team_id]
    if status is not None:
        conditions.append(Application.status == status)
    if pending_only:
        conditions.append(Application.status.in_(("submitted", "reviewing")))
    rows = (
        await session.execute(
            _applicant_statement()
            .where(*conditions)
            .order_by(
                Application.submitted_at.desc(), Application.application_id.desc()
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [ApplicantRecord(*row) for row in rows]


async def get_applicant_record(
    session: AsyncSession, application_id: UUID
) -> ApplicantRecord:
    row = (
        await session.execute(
            _applicant_statement().where(Application.application_id == application_id)
        )
    ).one()
    return ApplicantRecord(*row)


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


async def list_selection_related_ids(
    session: AsyncSession,
    applicant_id: UUID,
    contest_id: UUID,
    application_id: UUID,
    *,
    pending_statuses: tuple[str, ...],
) -> list[tuple[UUID, UUID]]:
    rows = (
        await session.execute(
            select(Application.application_id, Application.team_id).where(
                Application.applicant_account_id == applicant_id,
                Application.contest_id == contest_id,
                or_(
                    Application.application_id == application_id,
                    Application.status.in_(pending_statuses),
                ),
            )
        )
    ).all()
    return [(row[0], row[1]) for row in rows]


async def flush_application_changes(session: AsyncSession) -> None:
    """선발 유스케이스의 최종 응답 조회 전에 남은 변경을 flush한다."""
    await session.flush()
