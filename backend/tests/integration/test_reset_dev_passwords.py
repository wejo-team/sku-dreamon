"""개발 비밀번호 갱신의 계정 범위·멱등성·기존 세션 보존을 검사한다."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demo_data import DEV_ACCOUNT_IDS
from app.models.auth import Account
from app.schemas.auth import SignupCredentials
from app.security.passwords import hash_password, verify_password
from app.services.sessions import issue_session
from scripts.reset_dev_passwords import reset_accounts
from scripts.seed_dev_data import DEV_PASSWORD

pytest_plugins = ["tests.integration.test_auth_models"]
pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_only_seed_account_changes_and_existing_session_is_preserved(
    auth_session: AsyncSession,
) -> None:
    old_hash = await hash_password("previous test password")
    seed = Account(
        account_id=DEV_ACCOUNT_IDS[0],
        login_id_normalized="devuser001",
        password_hash=old_hash,
    )
    ordinary = Account(
        account_id=uuid4(), login_id_normalized="ordinaryuser", password_hash=old_hash
    )
    auth_session.add_all([seed, ordinary])
    await auth_session.flush()
    issued = await issue_session(auth_session, seed.account_id)
    await auth_session.commit()
    session_times = (
        issued.session.created_at,
        issued.session.last_seen_at,
        issued.session.expires_at,
    )
    credentials = SignupCredentials.model_validate(
        {"loginId": "devuser001", "password": DEV_PASSWORD}
    )
    now = datetime.now(UTC)
    assert await reset_accounts(auth_session, credentials, now) == (1, 1, 299)
    await auth_session.commit()
    assert await verify_password(seed.password_hash, DEV_PASSWORD)
    assert seed.credentials_updated_at == now
    assert ordinary.password_hash == old_hash
    new_hash = seed.password_hash
    assert await reset_accounts(auth_session, credentials, datetime.now(UTC)) == (
        1,
        0,
        299,
    )
    assert seed.password_hash == new_hash
    assert seed.credentials_updated_at == now
    await auth_session.refresh(issued.session)
    assert issued.session.revoked_at is None
    assert (
        issued.session.created_at,
        issued.session.last_seen_at,
        issued.session.expires_at,
    ) == session_times


async def test_identity_collision_rejects_all_changes_before_hashing(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = Account(
        account_id=DEV_ACCOUNT_IDS[0],
        login_id_normalized="devuser001",
        password_hash="untouched",
    )
    collision = Account(
        account_id=DEV_ACCOUNT_IDS[1],
        login_id_normalized="differentuser",
        password_hash="untouched",
    )
    auth_session.add_all([first, collision])
    await auth_session.commit()

    async def forbidden_verify(stored: str, value: str) -> bool:
        pytest.fail("식별자 충돌 검사 전에 해시를 검증하면 안 됩니다.")

    monkeypatch.setattr("scripts.reset_dev_passwords.verify_password", forbidden_verify)
    credentials = SignupCredentials.model_validate(
        {"loginId": "devuser001", "password": DEV_PASSWORD}
    )
    with pytest.raises(ValueError, match="충돌"):
        await reset_accounts(auth_session, credentials, datetime.now(UTC))
    assert first.password_hash == collision.password_hash == "untouched"


@pytest.mark.parametrize("unchanged", [False, True])
async def test_slow_batches_keep_transaction_alive_and_remain_rollbackable(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, unchanged: bool
) -> None:
    original_hash = "new-test-hash" if unchanged else "old-test-hash"
    auth_session.add_all(
        Account(
            account_id=account_id,
            login_id_normalized=f"devuser{index + 1:03d}",
            password_hash=original_hash,
        )
        for index, account_id in enumerate(DEV_ACCOUNT_IDS[:31])
    )
    await auth_session.commit()

    async def slow_verify(stored: str, password: str) -> bool:
        # 실제 Argon2 처리 중 SQL이 없는 구간을 짧은 테스트 시간으로 재현한다.
        await asyncio.sleep(0.08)
        return stored == "new-test-hash"

    async def test_hash(password: str) -> str:
        return "new-test-hash"

    monkeypatch.setattr("scripts.reset_dev_passwords.verify_password", slow_verify)
    monkeypatch.setattr("scripts.reset_dev_passwords.hash_password", test_hash)
    await auth_session.execute(
        text("SET LOCAL idle_in_transaction_session_timeout = '2s'")
    )
    credentials = SignupCredentials.model_validate(
        {"loginId": "devuser001", "password": DEV_PASSWORD}
    )
    result = await reset_accounts(auth_session, credentials, datetime.now(UTC))
    assert result == (31, 0 if unchanged else 31, 269)
    assert set(await auth_session.scalars(select(Account.password_hash))) == {
        "new-test-hash"
    }
    # 중간 flush는 commit이 아니므로 전체 작업을 되돌릴 수 있어야 한다.
    await auth_session.rollback()
    assert set(await auth_session.scalars(select(Account.password_hash))) == {
        original_hash
    }
