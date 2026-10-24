"""공고 원문·접수 일정과 대상·분야 연결 테이블을 추가한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_02"
down_revision: str | Sequence[str] | None = "20261024_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Python 3.13 str.isspace()의 문자집합을 고정해 PostgreSQL locale과 무관하게 검사한다.
_REQUIRED_TEXT_WHITESPACE = (
    r"\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020"
    r"\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007"
    r"\2008\2009\200A\2028\2029\202F\205F\3000"
)


def upgrade() -> None:
    op.create_table(
        "contests",
        sa.Column("contest_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("organizer_name", sa.Text(), nullable=False),
        sa.Column("official_url", sa.Text(), nullable=False),
        sa.Column("eligibility_text", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("submission_details", sa.Text(), nullable=True),
        sa.Column("awards", sa.Text(), nullable=True),
        sa.Column("contact_info", sa.Text(), nullable=True),
        sa.Column("poster_url", sa.Text(), nullable=True),
        sa.Column("member_limit_kind", sa.String(length=16), nullable=False),
        sa.Column("min_members", sa.BigInteger(), nullable=True),
        sa.Column("max_members", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "version", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("registration_opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registration_closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open_source_date", sa.Date(), nullable=False),
        sa.Column("open_source_time", sa.Time(), nullable=True),
        sa.Column("open_source_timezone", sa.Text(), nullable=True),
        sa.Column("open_effective_timezone", sa.Text(), nullable=False),
        sa.Column("open_timezone_assumed", sa.Boolean(), nullable=False),
        sa.Column("close_source_date", sa.Date(), nullable=False),
        sa.Column("close_source_time", sa.Time(), nullable=True),
        sa.Column("close_source_timezone", sa.Text(), nullable=True),
        sa.Column("close_effective_timezone", sa.Text(), nullable=False),
        sa.Column("close_time_assumed", sa.Boolean(), nullable=False),
        sa.Column("close_timezone_assumed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(member_limit_kind = 'range' AND min_members IS NOT NULL "
            "AND max_members IS NOT NULL AND min_members > 0 "
            "AND max_members >= min_members) OR "
            "(member_limit_kind = 'unlimited' AND max_members IS NULL "
            "AND (min_members IS NULL OR min_members > 0)) OR "
            "(member_limit_kind = 'unknown' AND min_members IS NULL "
            "AND max_members IS NULL)",
            name=op.f("ck_contests_member_limit"),
        ),
        sa.CheckConstraint(
            " AND ".join(
                f"btrim({column}, U&'{_REQUIRED_TEXT_WHITESPACE}') <> ''"
                for column in (
                    "title",
                    "organizer_name",
                    "eligibility_text",
                    "official_url",
                )
            ),
            name=op.f("ck_contests_required_text"),
        ),
        sa.CheckConstraint(
            "close_time_assumed = (close_source_time IS NULL) "
            "AND close_timezone_assumed = (close_source_timezone IS NULL) "
            "AND open_timezone_assumed = (open_source_timezone IS NULL)",
            name=op.f("ck_contests_deadline_assumptions"),
        ),
        sa.CheckConstraint(
            "registration_opens_at < registration_closes_at",
            name=op.f("ck_contests_period"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_contests_version")),
        sa.PrimaryKeyConstraint("contest_id", name=op.f("pk_contests")),
    )
    op.create_index(
        "ix_contests_closes",
        "contests",
        ["registration_closes_at", "contest_id"],
        unique=False,
    )
    op.create_index(
        "ix_contests_created",
        "contests",
        [sa.literal_column("created_at DESC"), sa.literal_column("contest_id DESC")],
        unique=False,
    )
    op.create_table(
        "contest_audiences",
        sa.Column("contest_id", sa.Uuid(), nullable=False),
        sa.Column("audience_code", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "audience_code IN ('student', 'general', 'unrestricted', 'unknown')",
            name=op.f("ck_contest_audiences_code"),
        ),
        sa.ForeignKeyConstraint(
            ["contest_id"],
            ["contests.contest_id"],
            name="fk_contest_audiences_contest",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "contest_id", "audience_code", name=op.f("pk_contest_audiences")
        ),
    )
    op.create_table(
        "contest_fields",
        sa.Column("contest_id", sa.Uuid(), nullable=False),
        sa.Column("field_code", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["contest_id"],
            ["contests.contest_id"],
            name="fk_contest_fields_contest",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "contest_id", "field_code", name=op.f("pk_contest_fields")
        ),
    )
    op.create_index(
        "ix_contest_fields_field",
        "contest_fields",
        ["field_code", "contest_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_contest_fields_field", table_name="contest_fields")
    op.drop_table("contest_fields")
    op.drop_table("contest_audiences")
    op.drop_index("ix_contests_created", table_name="contests")
    op.drop_index("ix_contests_closes", table_name="contests")
    op.drop_table("contests")
