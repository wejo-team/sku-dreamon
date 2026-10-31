"""학수번호 단위 과목 원장과 프로필 선택 과목을 추가한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261031_10"
down_revision: str | Sequence[str] | None = "20261026_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column(
            "course_id", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "departments",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.CheckConstraint("course_id > 0", name="ck_courses_id"),
        sa.CheckConstraint(
            "btrim(code) <> '' AND btrim(name) <> ''", name="ck_courses_text"
        ),
        sa.PrimaryKeyConstraint("course_id", name="pk_courses"),
        sa.UniqueConstraint("code", name="uq_courses_code"),
    )
    op.create_table(
        "profile_courses",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["profiles.profile_id"],
            name="fk_profile_courses_profile",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.course_id"],
            name="fk_profile_courses_course",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", "course_id", name="pk_profile_courses"),
    )
    op.create_index(
        "ix_profile_courses_course", "profile_courses", ["course_id", "account_id"]
    )


def downgrade() -> None:
    op.drop_table("profile_courses")
    op.drop_table("courses")
