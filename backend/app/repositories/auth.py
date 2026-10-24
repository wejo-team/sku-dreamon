"""계정·서버 세션의 조회·행 잠금·flush를 수행한다."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Account, AuthSession
from app.models.profiles import Profile


async def add_session(session: AsyncSession, login_session: AuthSession) -> None:
    session.add(login_session)
    await session.flush()


async def add_account(session: AsyncSession, account: Account) -> None:
    session.add(account)
    await session.flush()


async def get_by_login_id(session: AsyncSession, login_id: str) -> Account | None:
    account: Account | None = await session.scalar(
        select(Account).where(Account.login_id_normalized == login_id)
    )
    return account


async def lock_session_by_token_hash(
    session: AsyncSession, token_hash: bytes
) -> AuthSession | None:
    login_session = await session.scalar(
        select(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .with_for_update()
    )
    return login_session


async def lock_session(
    session: AsyncSession,
    auth_session_id: UUID,
    account_id: UUID,
    token_hash: bytes,
) -> AuthSession | None:
    login_session = await session.scalar(
        select(AuthSession)
        .where(
            AuthSession.auth_session_id == auth_session_id,
            AuthSession.account_id == account_id,
            AuthSession.token_hash == token_hash,
        )
        .with_for_update()
    )
    return login_session


async def flush_session_changes(session: AsyncSession) -> None:
    await session.flush()


async def get_account_with_profile(
    session: AsyncSession, account_id: UUID
) -> tuple[Account, bool] | None:
    """계정과 프로필 존재 여부를 단일 SELECT로 읽는다."""
    result = await session.execute(
        select(
            Account,
            select(Profile.profile_id)
            .where(Profile.profile_id == Account.account_id)
            .exists(),
        ).where(Account.account_id == account_id)
    )
    row = result.one_or_none()
    return (row[0], row[1]) if row is not None else None
