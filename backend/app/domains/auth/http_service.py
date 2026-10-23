"""본인 계정 조회와 인증 HTTP의 트랜잭션 경계를 맡는다."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domains.auth.models import Account
from app.domains.auth.schemas import AccountResponse
from app.domains.auth.session_service import SessionPrincipal, revoke_session
from app.domains.demo.manifest import is_demo_account
from app.domains.profiles.models import Profile


async def get_account(session: AsyncSession, account_id: UUID) -> AccountResponse:
    """계정과 프로필 존재 여부를 같은 SELECT에서 읽는다."""
    result = await session.execute(
        select(
            Account,
            select(Profile.profile_id)
            .where(Profile.profile_id == Account.account_id)
            .exists(),
        ).where(Account.account_id == account_id)
    )
    row = result.one_or_none()
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


async def logout(session: AsyncSession, principal: SessionPrincipal) -> None:
    """현재 세션의 회수를 커밋하고, 실패 시 쿠키 변경 없이 롤백한다."""
    try:
        if not await revoke_session(session, principal):
            raise AppError(401, "UNAUTHENTICATED", "로그인이 필요합니다.")
        await session.commit()
    except Exception:
        await session.rollback()
        raise
