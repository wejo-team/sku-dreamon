"""현재 프로필과 선택 연결·포트폴리오의 저장 제약을 추가한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_04"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "version", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("real_name", sa.Text(), nullable=False),
        sa.Column(
            "is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("profile_image_code", sa.String(64), nullable=True),
        sa.Column("academic_status_code", sa.String(64), nullable=True),
        sa.Column("grade_code", sa.String(64), nullable=True),
        sa.Column("weekly_availability_code", sa.String(64), nullable=True),
        sa.Column("academic_unit_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "experience_state",
            sa.String(16),
            server_default=sa.text("'unspecified'"),
            nullable=False,
        ),
        sa.Column("experience_body", sa.Text(), nullable=True),
        sa.Column("introduction", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("version >= 1", name="ck_profiles_version"),
        sa.CheckConstraint("real_name <> ''", name="ck_profiles_real_name"),
        sa.CheckConstraint(
            "(experience_state IN ('unspecified', 'none') AND experience_body IS NULL) "
            "OR (experience_state = 'provided' AND experience_body IS NOT NULL "
            "AND experience_body <> '')",
            name="ck_profiles_experience",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["accounts.account_id"],
            name="fk_profiles_account",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["academic_unit_id"],
            ["academic_units.academic_unit_id"],
            name="fk_profiles_academic_unit",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("profile_id", name="pk_profiles"),
    )
    op.create_index("ix_profiles_academic_unit", "profiles", ["academic_unit_id"])
    op.create_index(
        "ix_profiles_public_updated",
        "profiles",
        [sa.text("updated_at DESC"), "profile_id"],
        postgresql_where=sa.text("is_public = true"),
    )
    for table_name, code_column, index_name in (
        ("profile_interests", "field_code", "ix_profile_interests_field"),
        ("profile_desired_roles", "role_code", "ix_profile_desired_roles_role"),
        ("profile_skills", "skill_code", "ix_profile_skills_skill"),
    ):
        op.create_table(
            table_name,
            sa.Column("account_id", sa.Uuid(), nullable=False),
            sa.Column(code_column, sa.String(64), nullable=False),
            sa.ForeignKeyConstraint(
                ["account_id"],
                ["profiles.profile_id"],
                name=f"fk_{table_name}_profile",
                ondelete="RESTRICT",
                onupdate="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("account_id", code_column, name=f"pk_{table_name}"),
        )
        op.create_index(index_name, table_name, [code_column, "account_id"])
    op.create_table(
        "portfolio_links",
        sa.Column("portfolio_link_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.CheckConstraint("url <> ''", name="ck_portfolio_links_url"),
        sa.ForeignKeyConstraint(
            ["portfolio_link_id"],
            ["profiles.profile_id"],
            name="fk_portfolio_links_profile",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("portfolio_link_id", name="pk_portfolio_links"),
    )


def downgrade() -> None:
    op.drop_table("portfolio_links")
    op.drop_table("profile_skills")
    op.drop_table("profile_desired_roles")
    op.drop_table("profile_interests")
    op.drop_table("profiles")
