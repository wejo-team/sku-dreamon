"""프로필의 저장 조회를 수행하고 ORM 행과 저장된 선택 코드를 반환한다."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profiles import (
    PortfolioLink,
    Profile,
    ProfileDesiredRole,
    ProfileInterest,
    ProfileSkill,
)


@dataclass(frozen=True)
class ProfileSearch:
    field_code: str | None
    role_code: str | None
    search: str
    matching_fields: tuple[str, ...]
    matching_roles: tuple[str, ...]
    matching_skills: tuple[str, ...]
    name_contains: str | None = None


async def list_portfolios(
    session: AsyncSession, account_ids: Sequence[UUID]
) -> Sequence[PortfolioLink]:
    return (
        await session.scalars(
            select(PortfolioLink).where(
                PortfolioLink.portfolio_link_id.in_(account_ids)
            )
        )
    ).all()


async def get_selection_codes(
    session: AsyncSession, account_ids: Sequence[UUID]
) -> tuple[dict[UUID, list[str]], dict[UUID, list[str]], dict[UUID, list[str]]]:
    fields: dict[UUID, list[str]] = {}
    roles: dict[UUID, list[str]] = {}
    skills: dict[UUID, list[str]] = {}
    if not account_ids:
        return fields, roles, skills
    for account_id, code in await session.execute(
        select(ProfileInterest.account_id, ProfileInterest.field_code)
        .where(ProfileInterest.account_id.in_(account_ids))
        .order_by(ProfileInterest.field_code)
    ):
        fields.setdefault(account_id, []).append(code)
    for account_id, code in await session.execute(
        select(ProfileDesiredRole.account_id, ProfileDesiredRole.role_code)
        .where(ProfileDesiredRole.account_id.in_(account_ids))
        .order_by(ProfileDesiredRole.role_code)
    ):
        roles.setdefault(account_id, []).append(code)
    for account_id, code in await session.execute(
        select(ProfileSkill.account_id, ProfileSkill.skill_code)
        .where(ProfileSkill.account_id.in_(account_ids))
        .order_by(ProfileSkill.skill_code)
    ):
        skills.setdefault(account_id, []).append(code)
    return fields, roles, skills


def _filters(query: ProfileSearch) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Profile.is_public.is_(True)]
    if query.name_contains is not None:
        conditions.append(
            Profile.real_name.icontains(query.name_contains, autoescape=True)
        )
    if query.field_code is not None:
        conditions.append(
            select(ProfileInterest.account_id)
            .where(
                ProfileInterest.account_id == Profile.profile_id,
                ProfileInterest.field_code == query.field_code,
            )
            .exists()
        )
    if query.role_code is not None:
        conditions.append(
            select(ProfileDesiredRole.account_id)
            .where(
                ProfileDesiredRole.account_id == Profile.profile_id,
                ProfileDesiredRole.role_code == query.role_code,
            )
            .exists()
        )
    search = query.search
    if search:
        conditions.append(
            or_(
                Profile.real_name.icontains(search, autoescape=True),
                Profile.introduction.icontains(search, autoescape=True),
                select(ProfileInterest.account_id)
                .where(
                    ProfileInterest.account_id == Profile.profile_id,
                    ProfileInterest.field_code.in_(query.matching_fields),
                )
                .exists(),
                select(ProfileDesiredRole.account_id)
                .where(
                    ProfileDesiredRole.account_id == Profile.profile_id,
                    ProfileDesiredRole.role_code.in_(query.matching_roles),
                )
                .exists(),
                select(ProfileSkill.account_id)
                .where(
                    ProfileSkill.account_id == Profile.profile_id,
                    ProfileSkill.skill_code.in_(query.matching_skills),
                )
                .exists(),
            )
        )
    return conditions


async def get_profile(
    session: AsyncSession, account_id: UUID, *, public_only: bool = False
) -> Profile | None:
    if not public_only:
        return await session.get(Profile, account_id)
    profile: Profile | None = await session.scalar(
        select(Profile).where(
            Profile.profile_id == account_id, Profile.is_public.is_(True)
        )
    )
    return profile


async def count_people(session: AsyncSession, query: ProfileSearch) -> int:
    conditions = _filters(query)
    total = await session.scalar(
        select(func.count()).select_from(Profile).where(*conditions)
    )
    assert total is not None
    return total


async def list_people(
    session: AsyncSession, query: ProfileSearch, *, page: int, page_size: int
) -> Sequence[Profile]:
    conditions = _filters(query)
    profiles = (
        await session.scalars(
            select(Profile)
            .where(*conditions)
            .order_by(Profile.updated_at.desc(), Profile.profile_id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return profiles
