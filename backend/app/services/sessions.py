"""로그인 세션의 발급·독립 활동 저장·현재 세션 회수 경계를 관리한다."""

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import Database
from app.models.auth import AuthSession

IDLE_LIFETIME = timedelta(hours=24)
ABSOLUTE_LIFETIME = timedelta(days=7)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


@dataclass(frozen=True)
class SessionPrincipal:
    """인증이 끝난 요청의 식별값이며 현재 업무 권한은 별도로 조회한다."""

    auth_session_id: UUID
    account_id: UUID
    token_hash: bytes = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class IssuedSession:
    """커밋 성공 뒤 쿠키로 보낼 원문과 호출자 트랜잭션의 저장 행이다."""

    token: str = field(repr=False)
    session: AuthSession


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_valid(session: AuthSession, now: datetime) -> bool:
    return (
        session.revoked_at is None
        and now < session.expires_at
        and now < session.last_seen_at + IDLE_LIFETIME
    )


async def issue_session(session: AsyncSession, account_id: UUID) -> IssuedSession:
    """계정 저장과 같은 트랜잭션에 세션을 추가하며 커밋은 호출자가 수행한다."""
    token = secrets.token_urlsafe(32)
    now = _utcnow()
    login_session = AuthSession(
        token_hash=hashlib.sha256(token.encode("ascii")).digest(),
        account_id=account_id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + ABSOLUTE_LIFETIME,
    )
    session.add(login_session)
    await session.flush()
    return IssuedSession(token=token, session=login_session)


async def authenticate_session(
    database: Database, token: str | None
) -> SessionPrincipal | None:
    """잠금 뒤 시각으로 유효성을 검사하고 활동만 독립적으로 커밋한다.

    업무 트랜잭션과 세션을 공유하지 않는다. DB 장애는 미인증으로 감추지
    않고 전파하며, 유효하지 않은 세션은 저장 내용을 바꾸지 않는다.
    """
    if token is None or _TOKEN_PATTERN.fullmatch(token) is None:
        return None
    token_hash = hashlib.sha256(token.encode("ascii")).digest()
    async with database.session() as session:
        login_session = await session.scalar(
            select(AuthSession)
            .where(AuthSession.token_hash == token_hash)
            .with_for_update()
        )
        now = _utcnow()
        if login_session is None or not _is_valid(login_session, now):
            return None
        # 서버 시계의 작은 역행으로 이미 기록한 활동 시각을 되돌리지 않는다.
        login_session.last_seen_at = max(login_session.last_seen_at, now)
        principal = SessionPrincipal(
            auth_session_id=login_session.auth_session_id,
            account_id=login_session.account_id,
            token_hash=login_session.token_hash,
            expires_at=login_session.expires_at,
        )
        await session.commit()
        return principal


async def revoke_session(session: AsyncSession, principal: SessionPrincipal) -> bool:
    """현재 세션만 회수하며 쿠키 삭제 전 커밋은 상위 로그아웃 서비스가 맡는다."""
    login_session = await session.scalar(
        select(AuthSession)
        .where(
            AuthSession.auth_session_id == principal.auth_session_id,
            AuthSession.account_id == principal.account_id,
            AuthSession.token_hash == principal.token_hash,
        )
        .with_for_update()
    )
    now = _utcnow()
    if login_session is None or not _is_valid(login_session, now):
        return False
    login_session.revoked_at = max(now, login_session.created_at)
    await session.flush()
    return True
