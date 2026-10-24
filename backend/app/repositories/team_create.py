"""생성 재시도 조회와 팀·역할·팀장 소속을 저장한다."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.applications import Application
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole


async def find_request(
    session: AsyncSession, account_id: UUID, request_id: UUID
) -> Team | None:
    team: Team | None = await session.scalar(
        select(Team)
        .where(Team.leader_account_id == account_id, Team.request_id == request_id)
        .execution_options(populate_existing=True)
    )
    return team


async def pending_ids(
    session: AsyncSession, account_id: UUID, contest_id: UUID
) -> list[tuple[UUID, UUID]]:
    rows = await session.execute(
        select(Application.application_id, Application.team_id).where(
            Application.applicant_account_id == account_id,
            Application.contest_id == contest_id,
            Application.status.in_(("submitted", "reviewing")),
        )
    )
    return [(row[0], row[1]) for row in rows]


async def insert_team(
    session: AsyncSession, team: Team, membership: TeamMembership, roles: Sequence[str]
) -> None:
    session.add(team)
    await session.flush()
    session.add(membership)
    session.add_all(
        [TeamRecruitmentRole(team_id=team.team_id, role_code=code) for code in roles]
    )
    await session.flush()
