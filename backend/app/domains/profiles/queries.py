"""현재 공개 범위를 적용하고 같은 읽기 시점의 프로필·목록을 구성한다."""

from collections.abc import Sequence
from typing import Literal, cast
from uuid import UUID

from pydantic import AnyHttpUrl
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.domains.catalogs.codes import (
    AcademicStatusCode,
    FieldCode,
    GradeCode,
    ProfileImageCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
)
from app.domains.demo.manifest import is_demo_account
from app.domains.profiles.models import (
    PortfolioLink,
    Profile,
    ProfileDesiredRole,
    ProfileInterest,
    ProfileSkill,
)
from app.domains.profiles.schemas import (
    PeopleQuery,
    PersonSummary,
    PortfolioResponse,
    ProfileResponse,
)


async def _start_snapshot(session: AsyncSession) -> None:
    # 인증은 별도 세션에서 끝나며, 이 읽기 서비스가 요청 DB의 첫 접근을 소유한다.
    if session.in_transaction():
        raise RuntimeError(
            "Profile reads require a session without an active transaction"
        )
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


async def _selections(
    session: AsyncSession, account_ids: Sequence[UUID]
) -> tuple[
    dict[UUID, list[FieldCode]], dict[UUID, list[RoleCode]], dict[UUID, list[SkillCode]]
]:
    fields: dict[UUID, list[FieldCode]] = {}
    roles: dict[UUID, list[RoleCode]] = {}
    skills: dict[UUID, list[SkillCode]] = {}
    if not account_ids:
        return fields, roles, skills
    for account_id, code in await session.execute(
        select(ProfileInterest.account_id, ProfileInterest.field_code)
        .where(ProfileInterest.account_id.in_(account_ids))
        .order_by(ProfileInterest.field_code)
    ):
        fields.setdefault(account_id, []).append(FieldCode(code))
    for account_id, code in await session.execute(
        select(ProfileDesiredRole.account_id, ProfileDesiredRole.role_code)
        .where(ProfileDesiredRole.account_id.in_(account_ids))
        .order_by(ProfileDesiredRole.role_code)
    ):
        roles.setdefault(account_id, []).append(RoleCode(code))
    for account_id, code in await session.execute(
        select(ProfileSkill.account_id, ProfileSkill.skill_code)
        .where(ProfileSkill.account_id.in_(account_ids))
        .order_by(ProfileSkill.skill_code)
    ):
        skills.setdefault(account_id, []).append(SkillCode(code))
    return fields, roles, skills


def _summary(
    profile: Profile,
    fields: list[FieldCode],
    roles: list[RoleCode],
    skills: list[SkillCode],
) -> PersonSummary:
    return PersonSummary(
        account_id=profile.profile_id,
        real_name=profile.real_name,
        is_demo=is_demo_account(profile.profile_id),
        profile_image_code=(
            ProfileImageCode(profile.profile_image_code)
            if profile.profile_image_code is not None
            else None
        ),
        introduction=profile.introduction,
        field_codes=fields,
        role_codes=roles,
        skill_codes=skills,
    )


async def build_profile_response(
    session: AsyncSession, profile: Profile
) -> ProfileResponse:
    """호출자가 열람 권한을 확인한 프로필을 같은 세션의 관련 값과 조합한다.

    지원받은 팀장의 상세 조회도 이 함수를 사용할 수 있다. 권한·잠금·읽기
    시점은 호출자가 소유하며 이 함수는 트랜잭션을 시작하거나 저장하지 않는다.
    """
    responses = await build_profile_responses(session, [profile])
    return responses[profile.profile_id]


async def build_profile_responses(
    session: AsyncSession, profiles: Sequence[Profile]
) -> dict[UUID, ProfileResponse]:
    """허가된 프로필들의 관련 값을 일괄 조회한다. 권한·트랜잭션은 호출자 소유다."""
    if not profiles:
        return {}
    account_ids = [profile.profile_id for profile in profiles]
    fields, roles, skills = await _selections(session, account_ids)
    portfolios = {
        portfolio.portfolio_link_id: portfolio
        for portfolio in await session.scalars(
            select(PortfolioLink).where(
                PortfolioLink.portfolio_link_id.in_(account_ids)
            )
        )
    }
    return {
        profile.profile_id: _detail(
            profile,
            fields.get(profile.profile_id, []),
            roles.get(profile.profile_id, []),
            skills.get(profile.profile_id, []),
            portfolios.get(profile.profile_id),
        )
        for profile in profiles
    }


def _detail(
    profile: Profile,
    fields: list[FieldCode],
    roles: list[RoleCode],
    skills: list[SkillCode],
    portfolio: PortfolioLink | None,
) -> ProfileResponse:
    summary = _summary(
        profile,
        fields,
        roles,
        skills,
    )
    return ProfileResponse(
        **summary.model_dump(by_alias=False),
        version=str(profile.version),
        is_public=profile.is_public,
        updated_at=profile.updated_at,
        academic_status_code=(
            AcademicStatusCode(profile.academic_status_code)
            if profile.academic_status_code is not None
            else None
        ),
        grade_code=GradeCode(profile.grade_code)
        if profile.grade_code is not None
        else None,
        weekly_availability_code=(
            WeeklyAvailabilityCode(profile.weekly_availability_code)
            if profile.weekly_availability_code is not None
            else None
        ),
        academic_unit_id=str(profile.academic_unit_id)
        if profile.academic_unit_id is not None
        else None,
        experience_state=cast(
            Literal["unspecified", "none", "provided"], profile.experience_state
        ),
        experience_body=profile.experience_body,
        portfolio=(
            PortfolioResponse(url=AnyHttpUrl(portfolio.url), title=portfolio.title)
            if portfolio is not None
            else None
        ),
    )


async def get_own_profile(session: AsyncSession, account_id: UUID) -> ProfileResponse:
    """인증된 본인에게 비공개를 포함한 현재 프로필을 반환한다."""
    await _start_snapshot(session)
    profile = await session.get(Profile, account_id)
    if profile is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
    return await build_profile_response(session, profile)


async def get_public_profile(
    session: AsyncSession, account_id: UUID
) -> ProfileResponse:
    """일반 상세에서는 본인·팀장 여부와 관계없이 공개된 프로필만 반환한다."""
    await _start_snapshot(session)
    profile = await session.scalar(
        select(Profile).where(
            Profile.profile_id == account_id, Profile.is_public.is_(True)
        )
    )
    if profile is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
    return await build_profile_response(session, profile)


def _filters(query: PeopleQuery) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Profile.is_public.is_(True)]
    if query.field_code is not None:
        conditions.append(
            select(ProfileInterest.account_id)
            .where(
                ProfileInterest.account_id == Profile.profile_id,
                ProfileInterest.field_code == query.field_code.value,
            )
            .exists()
        )
    if query.role_code is not None:
        conditions.append(
            select(ProfileDesiredRole.account_id)
            .where(
                ProfileDesiredRole.account_id == Profile.profile_id,
                ProfileDesiredRole.role_code == query.role_code.value,
            )
            .exists()
        )
    search = (query.q or "").strip()
    if search:
        needle = search.casefold()
        matching_fields = [
            code.value for code in FieldCode if needle in code.display_name.casefold()
        ]
        matching_roles = [
            code.value for code in RoleCode if needle in code.display_name.casefold()
        ]
        matching_skills = [
            code.value for code in SkillCode if needle in code.display_name.casefold()
        ]
        conditions.append(
            or_(
                Profile.real_name.icontains(search, autoescape=True),
                Profile.introduction.icontains(search, autoescape=True),
                select(ProfileInterest.account_id)
                .where(
                    ProfileInterest.account_id == Profile.profile_id,
                    ProfileInterest.field_code.in_(matching_fields),
                )
                .exists(),
                select(ProfileDesiredRole.account_id)
                .where(
                    ProfileDesiredRole.account_id == Profile.profile_id,
                    ProfileDesiredRole.role_code.in_(matching_roles),
                )
                .exists(),
                select(ProfileSkill.account_id)
                .where(
                    ProfileSkill.account_id == Profile.profile_id,
                    ProfileSkill.skill_code.in_(matching_skills),
                )
                .exists(),
            )
        )
    return conditions


async def list_people(session: AsyncSession, query: PeopleQuery) -> Page[PersonSummary]:
    """공개 검색 결과와 집계를 같은 스냅샷에서 읽고 마지막 페이지로 보정한다."""
    await _start_snapshot(session)
    conditions = _filters(query)
    total = await session.scalar(
        select(func.count()).select_from(Profile).where(*conditions)
    )
    assert total is not None
    total_pages = (total + query.page_size - 1) // query.page_size
    page = min(query.page, max(total_pages, 1))
    profiles = (
        await session.scalars(
            select(Profile)
            .where(*conditions)
            .order_by(Profile.updated_at.desc(), Profile.profile_id.asc())
            .offset((page - 1) * query.page_size)
            .limit(query.page_size)
        )
    ).all()
    fields, roles, skills = await _selections(
        session, [profile.profile_id for profile in profiles]
    )
    return Page(
        data=[
            _summary(
                profile,
                fields.get(profile.profile_id, []),
                roles.get(profile.profile_id, []),
                skills.get(profile.profile_id, []),
            )
            for profile in profiles
        ],
        pagination=PageMeta(
            page=page, page_size=query.page_size, total=total, total_pages=total_pages
        ),
    )
