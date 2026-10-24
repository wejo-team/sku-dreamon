"""본인 계정 조회와 인증 HTTP의 트랜잭션 경계를 맡는다."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demo_data import is_demo_account
from app.core.exceptions import AppError
from app.repositories import auth as auth_repository
from app.schemas.auth import AccountResponse


async def get_account(session: AsyncSession, account_id: UUID) -> AccountResponse:
    """계정과 프로필 존재 여부를 같은 SELECT에서 읽는다."""
    row = await auth_repository.get_account_with_profile(session, account_id)
    if row is None:
        raise AppError(401, "UNAUTHENTICATED", "로그인이 필요합니다.")
    account, has_profile = row
    return AccountResponse(
        id=account.account_id,
        login_id=account.login_id_normalized,
        is_demo=is_demo_account(account.account_id),
        has_profile=has_profile,
        school_verification="unverified",
        created_at=account.created_at,
    )
