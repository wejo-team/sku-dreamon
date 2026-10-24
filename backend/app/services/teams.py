"""같은 업무 세션의 팀·소속 변경을 담당한다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.teams import Team, TeamMembership


async def get_application_membership(
    session: AsyncSession, application_id: UUID
) -> TeamMembership | None:
    """지원 시도에 연결된 소속 이력을 같은 업무 세션에서 조회한다."""
    membership: TeamMembership | None = await session.scalar(
        select(TeamMembership).where(
            TeamMembership.source_application_id == application_id
        )
    )
    return membership


def end_application_membership(
    team: Team, membership: TeamMembership | None, *, now: datetime
) -> None:
    """호출자가 잠근 팀의 선발 소속을 종료하며 모집 상태는 보존한다."""
    if membership is None or membership.ended_at is not None:
        raise RuntimeError("Selected application requires active membership")
    membership.ended_at = now
    membership.end_reason = "application_canceled"
    team.version += 1
    team.updated_at = now
