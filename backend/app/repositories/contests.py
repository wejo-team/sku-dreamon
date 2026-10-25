"""공고 원문·분류·연결 팀 수를 한 SQL 읽기 시점에서 조회한다."""

from collections.abc import Sequence
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contests import Contest, ContestAudience, ContestField
from app.models.teams import Team


class ContestDetailRow(NamedTuple):
    contest: Contest
    field_codes: Sequence[str]
    audience_codes: Sequence[str]
    team_count: int


async def get_contest_detail(
    session: AsyncSession, contest_id: UUID
) -> ContestDetailRow | None:
    fields = (
        select(func.array_agg(ContestField.field_code))
        .where(ContestField.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    audiences = (
        select(func.array_agg(ContestAudience.audience_code))
        .where(ContestAudience.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    team_count = (
        select(func.count())
        .select_from(Team)
        .where(Team.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            select(Contest, fields, audiences, team_count)
            .where(Contest.contest_id == contest_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        return None
    contest, fields, audiences, team_count = row
    return ContestDetailRow(contest, fields or [], audiences or [], team_count)
