"""계정·프로필 잠금 아래 전체 저장·공개 전환과 버전 충돌을 처리한다."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.profiles import PortfolioLink, Profile
from app.repositories import profile_write as repository
from app.repositories.profiles import get_selection_codes
from app.repositories.recruitment_locks import lock_accounts
from app.rules.catalogs import (
    AcademicStatusCode,
    FieldCode,
    GradeCode,
    ProfileImageCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
    validate_catalog_selection,
)
from app.schemas.profile_write import ProfileWrite, VisibilityWrite
from app.schemas.profiles import ProfileResponse
from app.services.catalogs import validate_academic_selection
from app.services.profiles import build_profile_response


def _version_conflict() -> AppError:
    return AppError(409, "VERSION_CONFLICT", "프로필을 다시 조회한 뒤 저장해주세요.")


async def save_profile(
    session: AsyncSession, account_id: UUID, body: ProfileWrite
) -> ProfileResponse:
    try:
        await lock_accounts(session, [account_id])
        profile = await repository.lock_profile(session, account_id)
        version = 0 if profile is None else profile.version
        if version != int(body.expected_version):
            raise _version_conflict()
        previous = await get_selection_codes(session, [account_id])
        try:
            for enum, attr in (
                (ProfileImageCode, "profile_image_code"),
                (AcademicStatusCode, "academic_status_code"),
                (GradeCode, "grade_code"),
                (WeeklyAvailabilityCode, "weekly_availability_code"),
            ):
                validate_catalog_selection(
                    enum,
                    getattr(body, attr),
                    previous_code=getattr(profile, attr, None),
                )
            for selection_enum, values, old in zip(
                (FieldCode, RoleCode, SkillCode),
                (body.field_codes, body.role_codes, body.skill_codes),
                previous,
                strict=True,
            ):
                for code in values:
                    validate_catalog_selection(
                        selection_enum,
                        code,
                        previous_code=code if code in old.get(account_id, []) else None,
                    )
        except ValueError as error:
            raise AppError(
                409, "INVALID_CATALOG_SELECTION", "선택지를 다시 확인해주세요."
            ) from error
        unit_id = None if body.academic_unit_id is None else int(body.academic_unit_id)
        await validate_academic_selection(
            session, unit_id, None if profile is None else profile.academic_unit_id
        )
        if profile is None:
            profile = Profile(profile_id=account_id, is_public=False)
        for attr in (
            "real_name",
            "profile_image_code",
            "academic_status_code",
            "grade_code",
            "weekly_availability_code",
            "experience_state",
            "experience_body",
            "introduction",
        ):
            setattr(profile, attr, getattr(body, attr))
        profile.academic_unit_id = unit_id
        profile.version = version + 1
        profile.updated_at = datetime.now(UTC)
        await repository.store_profile(session, profile)
        portfolio = (
            None
            if body.portfolio is None
            else PortfolioLink(
                portfolio_link_id=account_id,
                url=str(body.portfolio.url),
                title=body.portfolio.title,
            )
        )
        await repository.replace_selections(
            session,
            account_id,
            fields=body.field_codes,
            roles=body.role_codes,
            skills=body.skill_codes,
            portfolio=portfolio,
        )
        result = await build_profile_response(session, profile)
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise


async def set_visibility(
    session: AsyncSession, account_id: UUID, body: VisibilityWrite
) -> ProfileResponse:
    try:
        await lock_accounts(session, [account_id])
        profile = await repository.lock_profile(session, account_id)
        if profile is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "프로필을 찾을 수 없습니다.")
        if profile.version != int(body.expected_version):
            raise _version_conflict()
        if profile.is_public != body.is_public:
            profile.is_public = body.is_public
            profile.version += 1
            profile.updated_at = datetime.now(UTC)
            await repository.store_profile(session, profile)
        result = await build_profile_response(session, profile)
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise
