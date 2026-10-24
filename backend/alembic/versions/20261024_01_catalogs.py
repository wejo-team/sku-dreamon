"""학사 단일 계층 테이블을 생성하고 검증되지 않은 운영 원장은 적재하지 않는다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_01"
down_revision: str | Sequence[str] | None = "20261024_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "academic_units",
        sa.Column(
            "academic_unit_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "is_selectable",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.CheckConstraint("academic_unit_id > 0", name="ck_academic_units_id"),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_academic_units_name"),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> academic_unit_id",
            name="ck_academic_units_self_parent",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["academic_units.academic_unit_id"],
            name="fk_academic_units_parent",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("academic_unit_id", name="pk_academic_units"),
    )
    op.create_index(
        "ix_academic_units_parent", "academic_units", ["parent_id", "academic_unit_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_academic_units_parent", table_name="academic_units")
    op.drop_table("academic_units")
