"""팀장 명령으로 모집 상태를 변경하고 같은 트랜잭션에서 결과를 확정한다."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domains.contests.models import Contest, ContestField
from app.domains.teams.locks import lock_contest, lock_teams
from app.domains.teams.models import Team, TeamMembership, TeamRecruitmentRole
from app.domains.teams.schemas import TeamSummary, build_team_summary


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _summary(
    session: AsyncSession,
    team: Team,
    contest: Contest,
    *,
    member_count: int,
    now: datetime,
) -> TeamSummary:
    fields = (
        await session.scalars(
            select(ContestField.field_code).where(
                ContestField.contest_id == team.contest_id
            )
        )
    ).all()
    roles = (
        await session.scalars(
            select(TeamRecruitmentRole.role_code).where(
                TeamRecruitmentRole.team_id == team.team_id
            )
        )
    ).all()
    return build_team_summary(
        team,
        contest,
        field_codes=fields,
        role_codes=roles,
        member_count=member_count,
        now=now,
    )


async def _change_recruitment(
    session: AsyncSession,
    team_id: UUID,
    account_id: UUID,
    *,
    expected_version: int,
    reopening: bool,
) -> TeamSummary:
    try:
        # 공고 ID는 불변이며 순서 확인용 조회 뒤 공고·팀 순서로 잠근다.
        contest_id = await session.scalar(
            select(Team.contest_id).where(Team.team_id == team_id)
        )
        if contest_id is None:
            raise AppError(404, "NOT_FOUND", "팀을 찾을 수 없습니다.")
        contest = await lock_contest(session, contest_id)
        teams = await lock_teams(session, [team_id])
        if contest is None or not teams:
            raise AppError(404, "NOT_FOUND", "팀을 찾을 수 없습니다.")
        team = teams[0]
        if team.leader_account_id != account_id:
            raise AppError(403, "FORBIDDEN", "팀장만 모집 상태를 변경할 수 있습니다.")
        if team.version != expected_version:
            raise AppError(409, "VERSION_CONFLICT", "팀 정보가 변경되었습니다.")
        if team.recruitment_state not in ("open", "closed"):
            raise AppError(
                409, "INVALID_RECRUITMENT_STATE", "모집 상태를 변경할 수 없습니다."
            )

        now = _utcnow()
        member_count = await session.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(TeamMembership.team_id == team_id, TeamMembership.ended_at.is_(None))
        )
        assert member_count is not None
        if reopening:
            if (
                not contest.registration_opens_at
                <= now
                < contest.registration_closes_at
            ):
                raise AppError(409, "CONTEST_NOT_OPEN", "공모전 접수 기간이 아닙니다.")
            if now >= team.recruitment_closes_at:
                raise AppError(
                    409, "RECRUITMENT_DEADLINE_PASSED", "팀 모집 기한이 지났습니다."
                )
            if member_count >= team.target_capacity:
                raise AppError(409, "TEAM_FULL", "팀 정원이 찼습니다.")
            if team.recruitment_state == "closed":
                team.recruitment_state = "open"
                team.closed_reason = None
                team.version += 1
                team.updated_at = now
        elif team.recruitment_state == "open":
            team.recruitment_state = "closed"
            team.closed_reason = "leader_closed"
            team.version += 1
            team.updated_at = now

        await session.flush()
        result = await _summary(
            session, team, contest, member_count=member_count, now=now
        )
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise


async def close_recruitment(
    session: AsyncSession, team_id: UUID, account_id: UUID, *, expected_version: int
) -> TeamSummary:
    """기존 지원·소속을 유지하며 이미 닫힌 모집의 사유·시각·버전은 보존한다."""
    return await _change_recruitment(
        session, team_id, account_id, expected_version=expected_version, reopening=False
    )


async def reopen_recruitment(
    session: AsyncSession, team_id: UUID, account_id: UUID, *, expected_version: int
) -> TeamSummary:
    """잠금 뒤 기한·정원을 검사하며 과거 지원이나 소속을 복원하지 않는다."""
    return await _change_recruitment(
        session, team_id, account_id, expected_version=expected_version, reopening=True
    )
