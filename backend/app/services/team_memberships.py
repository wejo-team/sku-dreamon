"""팀 공간의 읽기 스냅샷과 현재 소속·전체 프로필 열람 권한을 관리한다."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import Page
from app.queries import team_memberships as queries
from app.queries.profiles import build_profile_responses
from app.queries.teams import get_team_detail
from app.schemas.team_management import TeamSpace, WorkspaceTeam


async def _start_snapshot(session: AsyncSession) -> None:
    # 인증은 별도 세션에서 끝난다. 요청 DB의 첫 접근만 소유하며 끝의 rollback과
    # 연결 반환은 호출자가 관리하는 세션 수명에 맡긴다.
    if session.in_transaction():
        raise RuntimeError("Team reads require a session without an active transaction")
    await session.execute(
        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    )


async def list_workspace_teams(
    session: AsyncSession, account_id: UUID, *, page: int = 1, page_size: int = 20
) -> Page[WorkspaceTeam]:
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("invalid workspace pagination")
    await _start_snapshot(session)
    return await queries.list_workspace_teams(
        session, account_id, page=page, page_size=page_size
    )


async def get_team_space(
    session: AsyncSession, team_id: UUID, account_id: UUID
) -> TeamSpace:
    await _start_snapshot(session)
    team, current_membership = await queries.get_membership_context(
        session, team_id, account_id
    )
    if team is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
    if current_membership is None:
        raise AppError(403, "FORBIDDEN", "현재 소속된 팀만 확인할 수 있습니다.")
    is_leader = team.leader_account_id == account_id
    rows = await queries.list_member_profiles(session, team_id)
    if any(profile is None for _, profile, _ in rows):
        raise AppError(500, "INTERNAL_ERROR", "팀 정보를 불러올 수 없습니다.")
    # 누락을 먼저 실패시켰으므로 이 목록은 전체 현재 소속을 유지한다.
    members = [
        (membership, profile, role)
        for membership, profile, role in rows
        if profile is not None
    ]
    received_applicants = (
        await queries.get_received_applicant_ids(session, team_id)
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
        await queries.get_pending_application_count(session, team_id)
        if is_leader
        else None
    )
    return TeamSpace(
        team=await get_team_detail(session, team_id),
        members=queries.build_team_members(members, team.leader_account_id, profiles),
        viewer_role="leader" if is_leader else "member",
        pending_application_count=pending_count,
    )
