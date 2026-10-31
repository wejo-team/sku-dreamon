"""실제 차단 목록을 확인한 뒤 로컬 고정 개발 계정의 비밀번호만 갱신한다."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db.session import create_database
from app.core.demo_data import DEV_ACCOUNT_IDS
from app.models.auth import Account
from app.schemas.auth import SignupCredentials
from app.security.passwords import PasswordBlocklist, hash_password, verify_password
from scripts.dev_dataset import DATASET_VERSION
from scripts.seed_dev_data import DEV_PASSWORD as DEV_PASSWORD
from scripts.seed_dev_data import validate_target


def validate_password(
    blocklist_path: Path, blocklist_version: str
) -> tuple[SignupCredentials, str]:
    """DB 접근 전에 입력 규칙·차단 목록을 검사하고 검사한 파일의 해시를 반환한다."""
    credentials = SignupCredentials.model_validate(
        {"loginId": "devuser001", "password": DEV_PASSWORD}
    )
    before = hashlib.sha256(blocklist_path.read_bytes()).hexdigest()
    blocklist = PasswordBlocklist.from_file(blocklist_path, version=blocklist_version)
    after = hashlib.sha256(blocklist_path.read_bytes()).hexdigest()
    if before != after:
        raise ValueError("검사 중 차단 목록이 변경되었습니다. 다시 실행해주세요.")
    if blocklist.contains(credentials.password):
        raise ValueError("개발 비밀번호가 차단 목록에 포함되어 변경하지 않습니다.")
    return credentials, after


async def reset_accounts(
    session: AsyncSession, credentials: SignupCredentials, reference_at: datetime
) -> tuple[int, int, int]:
    """현재 비밀번호가 다른 고정 계정만 변경하며 커밋은 호출자가 담당한다.

    호출자는 검증한 개발 비밀번호를 전달한다. 기존 로그인 세션과 업무 데이터는
    변경하지 않으며, 누락된 계정을 새로 생성하지 않는다.
    """
    expected = {
        account_id: f"devuser{index + 1:03d}"
        for index, account_id in enumerate(DEV_ACCOUNT_IDS)
    }
    accounts = list(
        await session.scalars(
            select(Account)
            .where(Account.account_id.in_(DEV_ACCOUNT_IDS))
            .order_by(Account.account_id)
            .with_for_update()
        )
    )
    # 한 계정이라도 충돌하면 다른 계정의 해시를 만들거나 수정하기 전에 중단한다.
    for account in accounts:
        if account.login_id_normalized != expected[account.account_id]:
            raise ValueError("개발 계정 UUID와 로그인 아이디가 충돌합니다.")
    updated = 0
    for processed, account in enumerate(accounts, start=1):
        if not await verify_password(account.password_hash, credentials.password):
            account.password_hash = await hash_password(credentials.password)
            account.credentials_updated_at = reference_at
            updated += 1
        if processed % 10 == 0:
            # Argon2 처리 동안 DB 유휴 제한에 걸리지 않도록 작게 반영한다.
            # 변경 없는 재실행도 SQL을 보내며 전체 commit·rollback 경계는 유지한다.
            await session.flush()
            await session.execute(text("SELECT 1"))
    await session.flush()
    return len(accounts), updated, len(DEV_ACCOUNT_IDS) - len(accounts)


async def run(
    *, blocklist: Path, blocklist_version: str, apply: bool
) -> dict[str, object]:
    credentials, checksum = validate_password(blocklist, blocklist_version)
    url = str(Settings().database_url)
    validate_target(url)
    reference_at = datetime.now(UTC)
    database = create_database(url)
    try:
        async with database.session() as session:
            async with session.begin() as transaction:
                if (
                    await session.scalar(text("SELECT current_database()"))
                    != "wejo_dev"
                ):
                    raise ValueError("wejo_dev가 아닌 DB입니다.")
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(20261026, 300)")
                )
                checked, updated, missing = await reset_accounts(
                    session, credentials, reference_at
                )
                if not apply:
                    await transaction.rollback()
        return {
            "datasetVersion": DATASET_VERSION,
            "referenceAt": reference_at.isoformat(),
            "accountsChecked": checked,
            "passwordsUpdated": updated,
            "missingAccounts": missing,
            "blocklistVersion": blocklist_version,
            "blocklistSha256": checksum,
            "status": "applied" if apply else "rolled_back",
        }
    finally:
        await database.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocklist", type=Path, required=True)
    parser.add_argument("--blocklist-version", required=True)
    parser.add_argument(
        "--apply", action="store_true", help="검증 후 저장 (기본은 롤백)"
    )
    parser.add_argument("--report", type=Path, help="비밀값이 없는 결과 JSON 저장 경로")
    args = parser.parse_args()
    result = asyncio.run(
        run(
            blocklist=args.blocklist,
            blocklist_version=args.blocklist_version,
            apply=args.apply,
        )
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    report = args.report or (
        Path(__file__).resolve().parents[2]
        / "data/reports/dev-dataset"
        / DATASET_VERSION
        / f"password-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.json"
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
