"""같은 읽기 시점의 현재 소속과 팀 공간별 프로필 열람 범위를 적용한다."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.domains.applications.models import Application
from app.domains.catalogs.codes import RoleCode
from app.domains.contests.models import Contest, ContestField
from app.domains.demo.manifest import is_demo_account
from app.domains.profiles.models import Profile
from app.domains.profiles.queries import build_profile_responses
from app.domains.teams.management_schemas import TeamMember, TeamSpace, WorkspaceTeam
from app.domains.teams.models import Team, TeamMembership, TeamRecruitmentRole
from app.domains.teams.queries import get_team_detail
from app.domains.teams.schemas import build_team_summary


async def _start_snapshot(session: AsyncSession) -> None:
    # 인증은 별도 세션에서 끝난다. 요청 DB의 첫 접근만 소유하며 끝의 rollback과
    # 연결 반환은 호출자가 관리하는 세션 수명에 맡긴다.
    if session.in_transaction():
        raise RuntimeError("Team reads require a session without an active transaction")
    await session.execute(
        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    )


async def list_workspace_teams(
    session: AsyncSession,
    account_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> Page[WorkspaceTeam]:
    """현재 소속만 안정 정렬하며 총원·페이지·표시 집계를 같은 스냅샷에서 읽는다.

    진행 중인 트랜잭션이 없는 요청 전용 세션을 받는다. 이 함수는 다른 업무의
    트랜잭션을 종료하거나 커밋하지 않으며 반환 후 세션 정리는 호출자 책임이다.
    """
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("invalid workspace pagination")
    await _start_snapshot(session)
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


async def get_team_space(
    session: AsyncSession, team_id: UUID, account_id: UUID
) -> TeamSpace:
    """현재 소속을 먼저 검사하고 허가된 전체 프로필만 원본 DTO로 구성한다.

    목록 조회와 동일하게 활성 트랜잭션이 없는 요청 전용 세션을 받는다.
    """
    await _start_snapshot(session)
    team = await session.get(Team, team_id, populate_existing=True)
    if team is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
    current_membership = await session.scalar(
        select(TeamMembership).where(
            TeamMembership.team_id == team_id,
            TeamMembership.account_id == account_id,
            TeamMembership.ended_at.is_(None),
        )
    )
    if current_membership is None:
        raise AppError(403, "FORBIDDEN", "현재 소속된 팀만 확인할 수 있습니다.")
    is_leader = team.leader_account_id == account_id
    rows = (
        await session.execute(
            select(TeamMembership, Profile, Application.applied_role_code)
            .outerjoin(Profile, Profile.profile_id == TeamMembership.account_id)
            .outerjoin(
                Application,
                Application.application_id == TeamMembership.source_application_id,
            )
            .where(TeamMembership.team_id == team_id, TeamMembership.ended_at.is_(None))
            .order_by(TeamMembership.joined_at, TeamMembership.team_membership_id)
            .execution_options(populate_existing=True)
        )
    ).all()
    # 가입은 프로필 행을 보장하지 않는다. 필수 실명을 임의로 만들거나 현재
    # 팀원을 누락시키지 않고, 계약을 구성할 수 없는 데이터는 안전하게 실패한다.
    if any(profile is None for _, profile, _ in rows):
        raise AppError(500, "INTERNAL_ERROR", "팀 정보를 불러올 수 없습니다.")
    received_applicants = (
        set(
            await session.scalars(
                select(Application.applicant_account_id)
                .where(Application.team_id == team_id)
                .distinct()
            )
        )
        if is_leader
        else set()
    )
    allowed_profiles = [
        profile
        for _, profile, _ in rows
        if profile.profile_id == account_id
        or profile.is_public
        or profile.profile_id in received_applicants
    ]
    profiles = await build_profile_responses(session, allowed_profiles)
    members = [
        TeamMember(
            membership_id=membership.team_membership_id,
            account_id=membership.account_id,
            real_name=profile.real_name,
            is_demo=is_demo_account(membership.account_id),
            membership_role=(
                "leader"
                if membership.account_id == team.leader_account_id
                else "member"
            ),
            role_code=(
                RoleCode(role_code)
                if membership.account_id != team.leader_account_id
                and role_code is not None
                else None
            ),
            joined_at=membership.joined_at,
            profile=profiles.get(membership.account_id),
        )
        for membership, profile, role_code in rows
    ]
    pending_count = (
        await session.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.team_id == team_id,
                Application.status.in_(("submitted", "reviewing")),
            )
        )
        if is_leader
        else None
    )
    return TeamSpace(
        team=await get_team_detail(session, team_id),
        members=members,
        viewer_role="leader" if is_leader else "member",
        pending_application_count=pending_count,
    )
