"""팀 공간의 읽기 스냅샷·열람 권한과 응답 구성을 관리한다."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import begin_read_snapshot
from app.core.demo_data import is_demo_account
from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.models.profiles import Profile
from app.models.teams import TeamMembership
from app.repositories import team_memberships as repository
from app.rules.catalogs import RoleCode
from app.schemas.profiles import ProfileResponse
from app.schemas.team_management import TeamMember, TeamSpace, WorkspaceTeam
from app.services.profiles import build_profile_responses
from app.services.teams import build_team_summary, get_team_detail


async def _start_snapshot(session: AsyncSession) -> None:
    # 인증은 별도 세션에서 끝난다. 요청 DB의 첫 접근만 소유하며 끝의 rollback과
    # 연결 반환은 호출자가 관리하는 세션 수명에 맡긴다.
    if session.in_transaction():
        raise RuntimeError("Team reads require a session without an active transaction")
    await begin_read_snapshot(session, read_only=True)


async def list_workspace_teams(
    session: AsyncSession, account_id: UUID, *, page: int = 1, page_size: int = 20
) -> Page[WorkspaceTeam]:
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("invalid workspace pagination")
    await _start_snapshot(session)
    result = await repository.list_workspace_teams(
        session, account_id, page=page, page_size=page_size
    )
    rows = result.rows
    fields, roles = result.field_codes, result.role_codes
    members, pending = result.member_counts, result.pending_counts
    pagination = PageMeta(
        page=result.page,
        page_size=page_size,
        total=result.total,
        total_pages=(result.total + page_size - 1) // page_size,
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
    await _start_snapshot(session)
    team, current_membership = await repository.get_membership_context(
        session, team_id, account_id
    )
    if team is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
    if current_membership is None:
        raise AppError(403, "FORBIDDEN", "현재 소속된 팀만 확인할 수 있습니다.")
    is_leader = team.leader_account_id == account_id
    rows = await repository.list_member_profiles(session, team_id)
    if any(profile is None for _, profile, _ in rows):
        raise AppError(500, "INTERNAL_ERROR", "팀 정보를 불러올 수 없습니다.")
    # 누락을 먼저 실패시켰으므로 이 목록은 전체 현재 소속을 유지한다.
    members = [
        (membership, profile, role)
        for membership, profile, role in rows
        if profile is not None
    ]
    received_applicants = (
        await repository.get_received_applicant_ids(session, team_id)
        if is_leader
        else set()
    )
    allowed_profiles = [
        profile
        for _, profile, _ in members
        if profile.profile_id == account_id
        or profile.is_public
        or profile.profile_id in received_applicants
    ]
    profiles = await build_profile_responses(session, allowed_profiles)
    pending_count = (
        await repository.get_pending_application_count(session, team_id)
        if is_leader
        else None
    )
    return TeamSpace(
        team=await get_team_detail(session, team_id),
        members=build_team_members(members, team.leader_account_id, profiles),
        viewer_role="leader" if is_leader else "member",
        pending_application_count=pending_count,
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
