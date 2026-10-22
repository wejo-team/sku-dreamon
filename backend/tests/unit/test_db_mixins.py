from collections.abc import Callable
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import BigInteger, ForeignKey, MetaData, Uuid, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import CreateTable

from app.core.db.base import Base
from app.core.db.mixins import CreatedAtMixin, UpdatedAtMixin
from app.core.db.types import UUIDPrimaryKey


class ModelBase(DeclarativeBase):
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)


class Account(CreatedAtMixin, UpdatedAtMixin, ModelBase):
    __tablename__ = "accounts"

    account_id: Mapped[UUIDPrimaryKey]


class Team(ModelBase):
    __tablename__ = "teams"

    team_id: Mapped[UUIDPrimaryKey]


class Profile(CreatedAtMixin, ModelBase):
    __tablename__ = "profiles"

    profile_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("accounts.account_id"), primary_key=True
    )


class AcademicUnit(ModelBase):
    __tablename__ = "academic_units"

    academic_unit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class Association(ModelBase):
    __tablename__ = "mixin_associations"

    owner_id: Mapped[int] = mapped_column(primary_key=True)
    option_code: Mapped[str] = mapped_column(primary_key=True)


def test_mixins_allow_independent_column_and_primary_key_choices() -> None:
    assert set(inspect(Account).columns.keys()) == {
        "account_id",
        "created_at",
        "updated_at",
    }
    assert set(inspect(Team).columns.keys()) == {"team_id"}
    assert set(inspect(Profile).columns.keys()) == {"profile_id", "created_at"}
    assert set(inspect(AcademicUnit).columns.keys()) == {"academic_unit_id"}
    assert set(inspect(Association).columns.keys()) == {"owner_id", "option_code"}
    assert [column.name for column in inspect(Association).primary_key] == [
        "owner_id",
        "option_code",
    ]
    assert ModelBase.metadata is not Base.metadata
    assert inspect(Account).registry is not Base.registry


@pytest.mark.parametrize(
    ("table_name", "key_name"), [("accounts", "account_id"), ("teams", "team_id")]
)
def test_uuid_primary_key_type_keeps_the_declared_column_name(
    table_name: str, key_name: str
) -> None:
    table = ModelBase.metadata.tables[table_name]
    dialect = cast(Callable[[], Dialect], postgresql.dialect)()
    ddl = str(CreateTable(table).compile(dialect=dialect))

    assert f"{key_name} UUID NOT NULL" in ddl
    assert [column.name for column in table.primary_key] == [key_name]
    assert table.c[key_name].default is not None
    assert table.c[key_name].server_default is None


def test_timestamp_mixins_keep_timezone_aware_db_defaults() -> None:
    table = ModelBase.metadata.tables["accounts"]
    dialect = cast(Callable[[], Dialect], postgresql.dialect)()
    ddl = str(CreateTable(table).compile(dialect=dialect))

    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert table.c.updated_at.onupdate is None


def test_shared_primary_key_reuses_its_parent_value_without_a_uuid_default() -> None:
    account_id = uuid4()
    account = Account(account_id=account_id)
    profile = Profile(profile_id=account.account_id)
    column = ModelBase.metadata.tables["profiles"].c.profile_id

    assert profile.profile_id == account_id
    assert column.primary_key
    assert {foreign_key.target_fullname for foreign_key in column.foreign_keys} == {
        "accounts.account_id"
    }
    assert column.default is None
    assert column.server_default is None
