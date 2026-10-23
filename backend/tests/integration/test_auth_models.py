"""PostgreSQL에서 계정·세션의 제약과 부분 가입 롤백을 검증한다."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateSchema

from app.core.db.base import Base
from app.core.db.session import create_database
from app.domains.auth.models import Account, AuthSession

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest_asyncio.fixture
async def auth_session(database_url: str) -> AsyncIterator[AsyncSession]:
    database = create_database(database_url)
    try:
        async with database.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = f"auth_test_{uuid4().hex}"
                await connection.execute(CreateSchema(schema))
                await connection.execution_options(schema_translate_map={None: schema})
                await connection.run_sync(
                    lambda sync: Base.metadata.create_all(
                        sync,
                        tables=[
                            Base.metadata.tables["accounts"],
                            Base.metadata.tables["auth_sessions"],
                        ],
                    )
                )
                async with AsyncSession(
                    connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session
            finally:
                await transaction.rollback()
    finally:
        await database.engine.dispose()


def make_account(login_id: str = "dreamon01") -> Account:
    return Account(login_id_normalized=login_id, password_hash="test-encoded-hash")


async def test_accounts_keep_generated_id_and_timezone_defaults(
    auth_session: AsyncSession,
) -> None:
    account = make_account()
    auth_session.add(account)
    await auth_session.commit()
    await auth_session.refresh(account)
    assert account.account_id is not None
    assert account.created_at.utcoffset() == timedelta(0)
    assert account.credentials_updated_at == account.created_at
    assert account.school_email is None
    assert account.school_email_verified_at is None


async def test_duplicate_login_ids_are_rejected_by_storage(
    auth_session: AsyncSession,
) -> None:
    auth_session.add(make_account())
    await auth_session.commit()
    auth_session.add(make_account())
    with pytest.raises(IntegrityError, match="uq_accounts_login_id"):
        await auth_session.flush()
    await auth_session.rollback()
    assert len((await auth_session.scalars(select(Account))).all()) == 1


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("login_id_normalized", "NotNormalized", "ck_accounts_login_id"),
        ("login_id_normalized", "bad_id", "ck_accounts_login_id"),
        ("password_hash", "", "ck_accounts_password_hash"),
        (
            "school_email_verified_at",
            datetime(2026, 10, 24, tzinfo=UTC),
            "ck_accounts_school_email_verified",
        ),
    ],
)
async def test_account_constraints_guard_direct_writes(
    auth_session: AsyncSession, field: str, value: object, constraint: str
) -> None:
    account = make_account()
    setattr(account, field, value)
    auth_session.add(account)
    with pytest.raises(IntegrityError, match=constraint):
        await auth_session.flush()


async def test_invalid_session_rolls_back_the_account_in_same_transaction(
    auth_session: AsyncSession,
) -> None:
    account = make_account()
    auth_session.add(account)
    await auth_session.flush()
    now = datetime.now(UTC)
    auth_session.add(
        AuthSession(
            token_hash=b"too-short",
            account_id=account.account_id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
    with pytest.raises(IntegrityError, match="ck_auth_sessions_token_hash"):
        await auth_session.commit()
    await auth_session.rollback()
    assert (await auth_session.scalars(select(Account))).all() == []
    assert (await auth_session.scalars(select(AuthSession))).all() == []


async def test_session_references_existing_account_and_cannot_outlive_its_delete(
    auth_session: AsyncSession,
) -> None:
    account = make_account()
    auth_session.add(account)
    await auth_session.flush()
    now = datetime.now(UTC)
    login_session = AuthSession(
        token_hash=b"a" * 32,
        account_id=account.account_id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=7),
    )
    auth_session.add(login_session)
    await auth_session.commit()
    assert login_session.auth_session_id != account.account_id
    await auth_session.delete(account)
    with pytest.raises(IntegrityError, match="fk_auth_sessions_account"):
        await auth_session.flush()


@pytest.mark.parametrize("bad_time", ["last_seen_at", "expires_at", "revoked_at"])
async def test_session_time_constraints_reject_invalid_ordering(
    auth_session: AsyncSession, bad_time: str
) -> None:
    account = make_account()
    auth_session.add(account)
    await auth_session.flush()
    now = datetime.now(UTC)
    login_session = AuthSession(
        token_hash=b"b" * 32,
        account_id=account.account_id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=7),
    )
    setattr(login_session, bad_time, now - timedelta(seconds=1))
    auth_session.add(login_session)
    with pytest.raises(IntegrityError, match="ck_auth_sessions_times"):
        await auth_session.flush()
