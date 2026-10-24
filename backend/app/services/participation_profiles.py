"""팀 생성·신규 지원 직전의 현재 필수 프로필과 공개 조건을 확인한다."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.repositories.profile_write import lock_profile
from app.repositories.profiles import get_selection_codes


async def require_profile(
    session: AsyncSession, account_id: UUID, *, public: bool
) -> None:
    """호출자가 계정을 먼저 잠그며, 공개 상태는 신규 지원에만 요구한다."""
    profile = await lock_profile(session, account_id)
    fields, roles, _ = await get_selection_codes(session, [account_id])
    if (
        profile is None
        or not profile.real_name.strip()
        or not fields.get(account_id)
        or not roles.get(account_id)
    ):
        raise AppError(409, "PROFILE_REQUIRED", "필수 프로필을 먼저 작성해주세요.")
    if public and not profile.is_public:
        raise AppError(409, "PROFILE_PRIVATE", "프로필 공개 후 지원해주세요.")
