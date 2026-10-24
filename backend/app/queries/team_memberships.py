"""호출자가 연 읽기 스냅샷에서 현재 소속과 팀 공간 자료를 조회한다."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demo_data import is_demo_account
from app.core.http.schemas import Page, PageMeta
from app.models.applications import Application
from app.models.contests import Contest, ContestField
from app.models.profiles import Profile
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole
from app.queries.teams import build_team_summary
from app.rules.catalogs import RoleCode
from app.schemas.profiles import ProfileResponse
from app.schemas.team_management import TeamMember, WorkspaceTeam


async def list_workspace_teams(
    session: AsyncSession,
    account_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> Page[WorkspaceTeam]:
    """현재 소속만 안정 정렬하며 총원·페이지·표시 집계를 같은 스냅샷에서 읽는다.

    호출자가 시작한 읽기 스냅샷에서 조회하며 트랜잭션을 변경하지 않는다.
    """
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
    pagination = PageMeta(
        page=current_page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )
    if total == 0:
        return Page[WorkspaceTeam](data=[], pagination=pagination)
    rows = (
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
    ).all()
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
    now = datetime.now(UTC)
    data = [
        WorkspaceTeam(
            team=build_team_summary(
                team,
                contest,
                field_codes=fields.get(contest.contest_id, []),
                role_codes=roles.get(team.team_id, []),
                member_count=members[team.team_id],
                now=now,
            ),
            membership_id=membership.team_membership_id,
            membership_role="leader"
            if team.leader_account_id == account_id
            else "member",
            role_code=(
                RoleCode(role_code)
                if team.leader_account_id != account_id and role_code is not None
                else None
            ),
            pending_application_count=(
                pending.get(team.team_id, 0)
                if team.leader_account_id == account_id
                else None
            ),
        )
        for membership, team, contest, role_code in rows
    ]
    return Page[WorkspaceTeam](data=data, pagination=pagination)


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


def build_team_members(
    rows: Sequence[tuple[TeamMembership, Profile, str | None]],
    leader_id: UUID,
    visible_profiles: Mapping[UUID, ProfileResponse],
) -> list[TeamMember]:
    """서비스가 허용한 전체 프로필만 이미 조회한 현재 소속 정보와 연결한다."""
    return [
        TeamMember(
            membership_id=membership.team_membership_id,
            account_id=membership.account_id,
            real_name=profile.real_name,
            is_demo=is_demo_account(membership.account_id),
            membership_role="leader"
            if membership.account_id == leader_id
            else "member",
            role_code=RoleCode(role_code)
            if membership.account_id != leader_id and role_code is not None
            else None,
            joined_at=membership.joined_at,
            profile=visible_profiles.get(membership.account_id),
        )
        for membership, profile, role_code in rows
    ]
