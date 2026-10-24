"""공고와 참가 대상·분야를 호출자의 같은 트랜잭션에 저장한다."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contests import Contest, ContestAudience, ContestField


async def insert_contest(
    session: AsyncSession,
    contest: Contest,
    *,
    audiences: Sequence[str],
    fields: Sequence[str],
) -> None:
    session.add(contest)
    await session.flush()
    session.add_all(
        [
            ContestAudience(contest_id=contest.contest_id, audience_code=code)
            for code in audiences
        ]
    )
    session.add_all(
        [
            ContestField(contest_id=contest.contest_id, field_code=code)
            for code in fields
        ]
    )
    await session.flush()
