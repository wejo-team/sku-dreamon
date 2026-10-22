from collections.abc import Callable
from typing import cast

import pytest
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base

POSTGRESQL_DIALECT = cast(Callable[[], Dialect], postgresql.dialect)()


@pytest.fixture
def metadata() -> MetaData:
    return MetaData(naming_convention=Base.metadata.naming_convention)


def test_generated_names_include_all_composite_columns(metadata: MetaData) -> None:
    Table(
        "parents",
        metadata,
        Column("first_id", Integer, primary_key=True),
        Column("second_id", Integer, primary_key=True),
    )
    child = Table(
        "children",
        metadata,
        Column("first_id", Integer, primary_key=True),
        Column("second_id", Integer, primary_key=True),
        UniqueConstraint("first_id", "second_id"),
        ForeignKeyConstraint(
            ["first_id", "second_id"], ["parents.first_id", "parents.second_id"]
        ),
        Index(None, "first_id", "second_id"),
    )

    names = {constraint.name for constraint in child.constraints}
    assert names == {
        "pk_children",
        "uq_children_first_id_second_id",
        "fk_children_first_id_second_id_parents",
    }
    index = next(iter(child.indexes))
    assert index.name == "ix_children_first_id_second_id"
    ddl = str(CreateTable(child).compile(dialect=POSTGRESQL_DIALECT))
    for name in names:
        assert f"CONSTRAINT {name}" in ddl
    assert "CREATE INDEX ix_children_first_id_second_id" in str(
        CreateIndex(index).compile(dialect=POSTGRESQL_DIALECT)
    )


def test_explicit_full_names_are_preserved_in_postgresql_ddl(
    metadata: MetaData,
) -> None:
    Table("accounts", metadata, Column("account_id", Integer, primary_key=True))
    sessions = Table(
        "auth_sessions",
        metadata,
        Column("auth_session_id", Integer),
        Column("account_id", Integer),
        Column("token_hash", String),
        PrimaryKeyConstraint("auth_session_id", name="pk_auth_sessions"),
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], name="fk_auth_sessions_account"
        ),
        CheckConstraint("token_hash <> ''", name="ck_auth_sessions_token_hash"),
        Index("ix_auth_sessions_account", "account_id"),
    )

    names = {constraint.name for constraint in sessions.constraints}
    assert names == {
        "pk_auth_sessions",
        "uq_auth_sessions_token_hash",
        "fk_auth_sessions_account",
        "ck_auth_sessions_token_hash",
    }
    ddl = str(CreateTable(sessions).compile(dialect=POSTGRESQL_DIALECT))
    for name in names:
        assert f"CONSTRAINT {name}" in ddl
    index = next(iter(sessions.indexes))
    assert index.name == "ix_auth_sessions_account"
    assert "CREATE INDEX ix_auth_sessions_account" in str(
        CreateIndex(index).compile(dialect=POSTGRESQL_DIALECT)
    )


def test_check_constraint_requires_an_explicit_name(metadata: MetaData) -> None:
    with pytest.raises(InvalidRequestError, match="requires.*explicitly named"):
        Table(
            "unnamed_checks",
            metadata,
            Column("value", Integer),
            CheckConstraint("value > 0"),
        )
