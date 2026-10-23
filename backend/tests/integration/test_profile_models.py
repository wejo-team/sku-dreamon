"""프로필의 공유 식별자·경험 조합·선택 중복 제약을 PostgreSQL에서 검증한다."""

from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import BigInteger, Column, MetaData, Table, Uuid, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.schema import CreateSchema

from app.core.db.session import create_database
from app.domains.profiles.models import (
    PortfolioLink,
    Profile,
    ProfileDesiredRole,
    ProfileInterest,
    ProfileSkill,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]

# 인증·학사 자체의 제약은 해당 도메인에서 검사하며 여기서는 참조 키만 제공한다.
metadata = MetaData()
accounts = Table("accounts", metadata, Column("account_id", Uuid, primary_key=True))
Table(
    "academic_units",
    metadata,
    Column("academic_unit_id", BigInteger, primary_key=True),
)
for model in (
    Profile,
    ProfileInterest,
    ProfileDesiredRole,
    ProfileSkill,
    PortfolioLink,
):
    cast(Table, model.__table__).to_metadata(metadata)
profiles = metadata.tables["profiles"]
portfolios = metadata.tables["portfolio_links"]


@pytest.fixture
async def profile_connection(database_url: str) -> AsyncIterator[AsyncConnection]:
    database = create_database(database_url)
    try:
        async with database.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = f"profile_test_{uuid4().hex}"
                await connection.execute(CreateSchema(schema))
                await connection.execution_options(schema_translate_map={None: schema})
                await connection.run_sync(metadata.create_all)
                yield connection
            finally:
                await transaction.rollback()
    finally:
        await database.engine.dispose()


async def test_profile_and_portfolio_share_the_account_identifier(
    profile_connection: AsyncConnection,
) -> None:
    account_id = uuid4()
    await profile_connection.execute(insert(accounts).values(account_id=account_id))
    await profile_connection.execute(
        insert(profiles).values(profile_id=account_id, real_name="예시 사용자")
    )
    await profile_connection.execute(
        insert(portfolios).values(
            portfolio_link_id=account_id, url="https://example.org/portfolio"
        )
    )
    row = (await profile_connection.execute(select(profiles))).mappings().one()
    assert row["profile_id"] == account_id
    assert row["version"] == 1
    assert row["is_public"] is False
    assert (row["experience_state"], row["experience_body"]) == ("unspecified", None)
    assert row["created_at"] == row["updated_at"]

    with pytest.raises(IntegrityError):
        async with profile_connection.begin_nested():
            await profile_connection.execute(
                insert(profiles).values(profile_id=uuid4(), real_name="고아 프로필")
            )

    with pytest.raises(IntegrityError):
        async with profile_connection.begin_nested():
            await profile_connection.execute(
                insert(portfolios).values(
                    portfolio_link_id=account_id, url="https://example.org/second"
                )
            )


@pytest.mark.parametrize(
    ("state", "body"),
    [("provided", None), ("provided", ""), ("none", "이전 본문"), ("unknown", None)],
)
async def test_invalid_experience_combination_is_rejected(
    profile_connection: AsyncConnection, state: str, body: str | None
) -> None:
    account_id = uuid4()
    await profile_connection.execute(insert(accounts).values(account_id=account_id))
    with pytest.raises(IntegrityError):
        await profile_connection.execute(
            insert(profiles).values(
                profile_id=account_id,
                real_name="예시 사용자",
                experience_state=state,
                experience_body=body,
            )
        )


@pytest.mark.parametrize(
    ("table_name", "column"),
    [
        ("profile_interests", "field_code"),
        ("profile_desired_roles", "role_code"),
        ("profile_skills", "skill_code"),
    ],
)
async def test_selection_cannot_be_duplicated_or_orphaned(
    profile_connection: AsyncConnection, table_name: str, column: str
) -> None:
    account_id = uuid4()
    await profile_connection.execute(insert(accounts).values(account_id=account_id))
    await profile_connection.execute(
        insert(profiles).values(profile_id=account_id, real_name="예시 사용자")
    )
    selection = metadata.tables[table_name]
    values = {"account_id": account_id, column: "EXAMPLE"}
    await profile_connection.execute(insert(selection).values(values))
    with pytest.raises(IntegrityError):
        async with profile_connection.begin_nested():
            await profile_connection.execute(insert(selection).values(values))
    with pytest.raises(IntegrityError):
        async with profile_connection.begin_nested():
            await profile_connection.execute(
                insert(selection).values({"account_id": uuid4(), column: "EXAMPLE"})
            )


async def test_profile_deletion_does_not_cascade_to_owned_data(
    profile_connection: AsyncConnection,
) -> None:
    account_id = uuid4()
    await profile_connection.execute(insert(accounts).values(account_id=account_id))
    await profile_connection.execute(
        insert(profiles).values(profile_id=account_id, real_name="예시 사용자")
    )
    await profile_connection.execute(
        insert(portfolios).values(
            portfolio_link_id=account_id, url="https://example.org/portfolio"
        )
    )
    with pytest.raises(IntegrityError):
        await profile_connection.execute(profiles.delete())
