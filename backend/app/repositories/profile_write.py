"""프로필 행 잠금과 전체 편집값·연결 집합 저장을 수행한다."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profiles import (
    PortfolioLink,
    Profile,
    ProfileDesiredRole,
    ProfileInterest,
    ProfileSkill,
)


async def lock_profile(session: AsyncSession, account_id: UUID) -> Profile | None:
    profile: Profile | None = await session.scalar(
        select(Profile)
        .where(Profile.profile_id == account_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return profile


async def store_profile(session: AsyncSession, profile: Profile) -> None:
    session.add(profile)
    await session.flush()


async def replace_selections(
    session: AsyncSession,
    account_id: UUID,
    *,
    fields: Sequence[str],
    roles: Sequence[str],
    skills: Sequence[str],
    portfolio: PortfolioLink | None,
) -> None:
    for model in (ProfileInterest, ProfileDesiredRole, ProfileSkill):
        await session.execute(delete(model).where(model.account_id == account_id))
    await session.execute(
        delete(PortfolioLink).where(PortfolioLink.portfolio_link_id == account_id)
    )
    session.add_all(
        [ProfileInterest(account_id=account_id, field_code=code) for code in fields]
    )
    session.add_all(
        [ProfileDesiredRole(account_id=account_id, role_code=code) for code in roles]
    )
    session.add_all(
        [ProfileSkill(account_id=account_id, skill_code=code) for code in skills]
    )
    if portfolio is not None:
        session.add(portfolio)
    await session.flush()
