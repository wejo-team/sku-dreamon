"""계정·서버 세션의 조회·행 잠금·flush를 수행한다."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import AuthSession


async def add_session(session: AsyncSession, login_session: AuthSession) -> None:
    session.add(login_session)
    await session.flush()


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
