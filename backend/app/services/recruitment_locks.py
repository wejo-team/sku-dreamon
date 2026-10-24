"""팀 업무가 공유하는 계정→공고→팀→지원의 구체적인 잠금 순서를 제공한다."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.applications import Application
from app.models.auth import Account
from app.models.contests import Contest
from app.models.teams import Team


async def lock_accounts(session: AsyncSession, account_ids: Sequence[UUID]) -> None:
    # NO KEY UPDATE는 다른 업무를 직렬화하면서 알림의 계정 FK 검사는 허용한다.
    await session.execute(
        select(Account.account_id)
        .where(Account.account_id.in_(account_ids))
        .order_by(Account.account_id)
        .with_for_update(key_share=True)
    )


async def lock_contest(session: AsyncSession, contest_id: UUID) -> Contest | None:
    return (
        await session.scalars(
            select(Contest)
            .where(Contest.contest_id == contest_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()


async def lock_teams(session: AsyncSession, team_ids: Sequence[UUID]) -> list[Team]:
    return list(
        await session.scalars(
            select(Team)
            .where(Team.team_id.in_(team_ids))
            .order_by(Team.team_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )


async def lock_applications(
    session: AsyncSession, application_ids: Sequence[UUID]
) -> list[Application]:
    return list(
        await session.scalars(
            select(Application)
            .where(Application.application_id.in_(application_ids))
            .order_by(Application.application_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
