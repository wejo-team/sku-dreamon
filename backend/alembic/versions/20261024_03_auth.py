"""자체 계정과 서버 로그인 세션 테이블을 생성한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_03"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("login_id_normalized", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "credentials_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("school_email", sa.String(320), nullable=True),
        sa.Column(
            "school_email_verified_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "login_id_normalized COLLATE \"C\" ~ '^[a-z0-9]{4,24}$'",
            name="ck_accounts_login_id",
        ),
        sa.CheckConstraint("password_hash <> ''", name="ck_accounts_password_hash"),
        sa.CheckConstraint(
            "school_email_verified_at IS NULL OR school_email IS NOT NULL",
            name="ck_accounts_school_email_verified",
        ),
        sa.PrimaryKeyConstraint("account_id", name="pk_accounts"),
        sa.UniqueConstraint("login_id_normalized", name="uq_accounts_login_id"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("auth_session_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name="ck_auth_sessions_token_hash"
        ),
        sa.CheckConstraint(
            "last_seen_at >= created_at AND expires_at > created_at "
            "AND (revoked_at IS NULL OR revoked_at >= created_at)",
            name="ck_auth_sessions_times",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name="fk_auth_sessions_account",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("auth_session_id", name="pk_auth_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_account", "auth_sessions", ["account_id"])
    op.create_index("ix_auth_sessions_expires", "auth_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_expires", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_account", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("accounts")
