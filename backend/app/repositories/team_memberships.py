"""현재 소속과 팀 공간 자료를 호출자가 연 읽기 스냅샷에서 조회한다."""

from collections.abc import Sequence
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.applications import Application
from app.models.contests import Contest, ContestField
from app.models.profiles import Profile
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole


class WorkspaceTeamsResult(NamedTuple):
    rows: Sequence[tuple[TeamMembership, Team, Contest, str | None]]
    field_codes: dict[UUID, list[str]]
    role_codes: dict[UUID, list[str]]
    member_counts: dict[UUID, int]
    pending_counts: dict[UUID, int]
    total: int
    page: int


async def list_workspace_teams(
    session: AsyncSession, account_id: UUID, *, page: int, page_size: int
) -> WorkspaceTeamsResult:
    membership_filter = (
        TeamMembership.account_id == account_id,
        TeamMembership.ended_at.is_(None),
    )
    total = (
        await session.scalar(
            select(func.count()).select_from(TeamMembership).where(*membership_filter)
        )
        or 0
    )
    total_pages = (total + page_size - 1) // page_size
    current_page = min(page, max(total_pages, 1))
    if total == 0:
        return WorkspaceTeamsResult([], {}, {}, {}, {}, total, current_page)
    rows = (
        (
            await session.execute(
                select(TeamMembership, Team, Contest, Application.applied_role_code)
                .join(Team, Team.team_id == TeamMembership.team_id)
                .join(Contest, Contest.contest_id == Team.contest_id)
                .outerjoin(
                    Application,
                    Application.application_id == TeamMembership.source_application_id,
                )
                .where(*membership_filter)
                .order_by(
                    TeamMembership.joined_at.desc(),
                    TeamMembership.team_membership_id.desc(),
                )
                .limit(page_size)
                .offset((current_page - 1) * page_size)
                .execution_options(populate_existing=True)
            )
        )
        .tuples()
        .all()
    )
    team_ids = [row[1].team_id for row in rows]
    contest_ids = [row[2].contest_id for row in rows]
    fields: dict[UUID, list[str]] = {}
    for contest_id, code in await session.execute(
        select(ContestField.contest_id, ContestField.field_code).where(
            ContestField.contest_id.in_(contest_ids)
        )
    ):
        fields.setdefault(contest_id, []).append(code)
    roles: dict[UUID, list[str]] = {}
    for team_id, code in await session.execute(
        select(TeamRecruitmentRole.team_id, TeamRecruitmentRole.role_code).where(
            TeamRecruitmentRole.team_id.in_(team_ids)
        )
    ):
        roles.setdefault(team_id, []).append(code)
    members = dict(
        (
            await session.execute(
                select(TeamMembership.team_id, func.count())
                .where(
                    TeamMembership.team_id.in_(team_ids),
                    TeamMembership.ended_at.is_(None),
                )
                .group_by(TeamMembership.team_id)
            )
        )
        .tuples()
        .all()
    )
    pending = dict(
        (
            await session.execute(
                select(Application.team_id, func.count())
                .where(
                    Application.team_id.in_(team_ids),
                    Application.status.in_(("submitted", "reviewing")),
                )
                .group_by(Application.team_id)
            )
        )
        .tuples()
        .all()
    )
    return WorkspaceTeamsResult(
        rows, fields, roles, members, pending, total, current_page
    )


async def get_membership_context(
    session: AsyncSession, team_id: UUID, account_id: UUID
) -> tuple[Team | None, TeamMembership | None]:
    row = (
        await session.execute(
            select(Team, TeamMembership)
            .outerjoin(
                TeamMembership,
                and_(
                    TeamMembership.team_id == Team.team_id,
                    TeamMembership.account_id == account_id,
                    TeamMembership.ended_at.is_(None),
                ),
            )
            .where(Team.team_id == team_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    return (None, None) if row is None else (row[0], row[1])


async def list_member_profiles(
    session: AsyncSession, team_id: UUID
) -> Sequence[tuple[TeamMembership, Profile | None, str | None]]:
    return (
        (
            await session.execute(
                select(TeamMembership, Profile, Application.applied_role_code)
                .outerjoin(Profile, Profile.profile_id == TeamMembership.account_id)
                .outerjoin(
                    Application,
                    Application.application_id == TeamMembership.source_application_id,
                )
                .where(
                    TeamMembership.team_id == team_id, TeamMembership.ended_at.is_(None)
                )
                .order_by(TeamMembership.joined_at, TeamMembership.team_membership_id)
                .execution_options(populate_existing=True)
            )
        )
        .tuples()
        .all()
    )


async def get_received_applicant_ids(session: AsyncSession, team_id: UUID) -> set[UUID]:
    return set(
        await session.scalars(
            select(Application.applicant_account_id)
            .where(Application.team_id == team_id)
            .distinct()
        )
    )


async def get_pending_application_count(session: AsyncSession, team_id: UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.team_id == team_id,
                Application.status.in_(("submitted", "reviewing")),
            )
        )
        or 0
    )
