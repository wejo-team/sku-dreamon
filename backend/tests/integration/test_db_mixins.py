from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import MetaData, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped
from sqlalchemy.schema import CreateSchema

from app.db.base import Base
from app.db.mixins import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin
from app.db.session import create_database

pytestmark = [pytest.mark.integration, pytest.mark.database]


class ModelBase(DeclarativeBase):
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)


class Record(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, ModelBase):
    __tablename__ = "mixin_records"

    title: Mapped[str]


async def test_uuid_and_timestamp_defaults_and_explicit_updates(
    database_url: str,
) -> None:
    assert ModelBase.registry is not Base.registry
    database = create_database(database_url)
    schema = f"wejo_mixin_test_{uuid4().hex}"
    try:
        async with database.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(CreateSchema(schema))
                await connection.execution_options(schema_translate_map={None: schema})
                await connection.run_sync(ModelBase.metadata.create_all)
                async with AsyncSession(connection, expire_on_commit=False) as session:
                    first = Record(title="first")
                    second = Record(title="second")
                    seed_id = uuid4()
                    seed_time = datetime(2026, 1, 1, tzinfo=UTC)
                    seeded = Record(
                        id=seed_id,
                        title="seeded",
                        created_at=seed_time,
                        updated_at=seed_time,
                    )
                    session.add_all([first, second, seeded])
                    await session.flush()

                    assert isinstance(first.id, UUID)
                    assert first.id != second.id
                    assert first.created_at.utcoffset() == timedelta(0)
                    assert first.created_at == first.updated_at
                    assert (seeded.id, seeded.created_at, seeded.updated_at) == (
                        seed_id,
                        seed_time,
                        seed_time,
                    )

                    created_at = first.created_at
                    await session.scalar(select(Record).where(Record.id == first.id))
                    await session.refresh(first)
                    assert first.updated_at == created_at

                    changed_at = created_at + timedelta(seconds=1)
                    first.title = "changed"
                    first.updated_at = changed_at
                    await session.flush()
                    await session.refresh(first)
                    assert first.created_at == created_at
                    assert first.updated_at == changed_at
            finally:
                await transaction.rollback()
    finally:
        await database.engine.dispose()
