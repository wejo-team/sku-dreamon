"""본인 계정 조회와 인증 HTTP의 트랜잭션 경계를 맡는다."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.auth import Account
from app.repositories import auth as auth_repository
from app.schemas.auth import AccountResponse, Credentials, LoginIdAvailability
from app.security.passwords import (
    PasswordBlocklist,
    hash_password,
    needs_password_rehash,
    verify_password,
)
from app.services.sessions import (
    IssuedSession,
    SessionPrincipal,
    issue_session,
    revoke_session,
)

_DUMMY_HASH = (
    "$argon2id$v=19$m=19456,t=2,p=1$ABgvEv7yyiwYlp/Zqsoe5g$"
    "F9vIyF9wEpSV2Qguma61Tktg48I4QzynZ3plXJr5sbg"
)


@dataclass(frozen=True)
class AuthenticatedAccount:
    account: AccountResponse
    issued: IssuedSession


async def login_id_availability(
    session: AsyncSession, login_id: str
) -> LoginIdAvailability:
    account = await auth_repository.get_by_login_id(session, login_id)
    return LoginIdAvailability(normalized_login_id=login_id, available=account is None)


async def signup(
    session: AsyncSession, credentials: Credentials, blocklist: PasswordBlocklist | None
) -> AuthenticatedAccount:
    try:
        if blocklist is None:
            raise AppError(
                503, "TEMPORARY_UNAVAILABLE", "가입을 잠시 후 다시 시도해주세요."
            )
        if blocklist.contains(credentials.password):
            raise AppError(400, "PASSWORD_BLOCKED", "다른 비밀번호를 선택해주세요.")
        account = Account(
            login_id_normalized=credentials.login_id,
            password_hash=await hash_password(credentials.password),
        )
        await auth_repository.add_account(session, account)
        issued = await issue_session(session, account.account_id)
        result = AuthenticatedAccount(
            await get_account(session, account.account_id), issued
        )
        await session.commit()
        return result
    except IntegrityError as error:
        await session.rollback()
        if getattr(
            error.orig, "sqlstate", None
        ) == "23505" and "uq_accounts_login_id" in str(error.orig):
            raise AppError(
                409, "LOGIN_ID_TAKEN", "이미 사용 중인 아이디입니다."
            ) from error
        raise
    except Exception:
        await session.rollback()
        raise


async def login(
    session: AsyncSession, credentials: Credentials
) -> AuthenticatedAccount:
    try:
        account = await auth_repository.get_by_login_id(session, credentials.login_id)
        valid = await verify_password(
            _DUMMY_HASH if account is None else account.password_hash,
            credentials.password,
        )
        if account is None or not valid:
            raise AppError(
                401, "INVALID_CREDENTIALS", "아이디와 비밀번호를 확인해주세요."
            )
        if needs_password_rehash(account.password_hash):
            account.password_hash = await hash_password(credentials.password)
        issued = await issue_session(session, account.account_id)
        result = AuthenticatedAccount(
            await get_account(session, account.account_id), issued
        )
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise


async def get_account(session: AsyncSession, account_id: UUID) -> AccountResponse:
    """계정과 프로필 존재 여부를 같은 SELECT에서 읽는다."""
    row = await auth_repository.get_account_with_profile(session, account_id)
    if row is None:
        raise AppError(401, "UNAUTHENTICATED", "로그인이 필요합니다.")
    account, has_profile = row
    return AccountResponse(
        id=account.account_id,
        login_id=account.login_id_normalized,
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
