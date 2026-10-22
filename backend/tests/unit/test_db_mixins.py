from collections.abc import Callable
from typing import cast

from sqlalchemy import BigInteger, MetaData, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.db.mixins import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin


class ModelBase(DeclarativeBase):
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)


class Entity(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, ModelBase):
    __tablename__ = "mixin_entities"


class AccountExtension(CreatedAtMixin, ModelBase):
    __tablename__ = "mixin_account_extensions"

    account_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class Association(ModelBase):
    __tablename__ = "mixin_associations"

    owner_id: Mapped[int] = mapped_column(primary_key=True)
    option_code: Mapped[str] = mapped_column(primary_key=True)


def test_mixins_allow_independent_column_and_primary_key_choices() -> None:
    assert set(inspect(Entity).columns.keys()) == {"id", "created_at", "updated_at"}
    assert set(inspect(AccountExtension).columns.keys()) == {"account_id", "created_at"}
    assert set(inspect(Association).columns.keys()) == {"owner_id", "option_code"}
    assert [column.name for column in inspect(Association).primary_key] == [
        "owner_id",
        "option_code",
    ]
    assert "mixin_entities" not in Base.metadata.tables
    assert inspect(Entity).registry is not Base.registry


def test_mixins_generate_native_uuid_and_timezone_aware_db_defaults() -> None:
    table = ModelBase.metadata.tables["mixin_entities"]
    dialect = cast(Callable[[], Dialect], postgresql.dialect)()
    ddl = str(CreateTable(table).compile(dialect=dialect))

    assert "id UUID NOT NULL" in ddl
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert table.c.id.server_default is None
    assert table.c.updated_at.onupdate is None
