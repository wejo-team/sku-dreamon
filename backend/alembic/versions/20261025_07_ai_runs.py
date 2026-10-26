"""대화 원문 없이 AI 실행 상태와 근거 검증 메타데이터를 저장한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261025_07"
down_revision: str | Sequence[str] | None = "20261024_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_runs",
        sa.Column("ai_run_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("auth_session_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("scope_key", sa.String(length=90), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("client_message_id", sa.Uuid(), nullable=True),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column(
            "request_fingerprint",
            sa.String(length=64),
            nullable=False,
            comment="정규화된 요청의 SHA-256. 입력 본문은 보존하지 않는다.",
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failure_code", sa.String(length=32), nullable=True),
        sa.Column(
            "references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment=(
                "권한 재검증용 리소스 ID·버전·해시. 프로필 전문과 답변을 넣지 않는다."
            ),
        ),
        sa.Column(
            "selected_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "result_hash",
            sa.String(length=64),
            nullable=True,
            comment="브라우저가 재전송한 결과의 위변조 확인용 SHA-256.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(purpose = 'chat' AND conversation_id IS NOT NULL AND "
            "client_message_id IS NOT NULL AND team_id IS NULL AND "
            "application_id IS NULL) OR (purpose = 'applicant_review' AND "
            "conversation_id IS NULL AND client_message_id IS NULL AND "
            "team_id IS NOT NULL AND application_id IS NOT NULL) OR (purpose "
            "= 'applicant_recommendation' AND conversation_id IS NULL AND "
            "client_message_id IS NULL AND team_id IS NOT NULL AND "
            "application_id IS NULL)",
            name=op.f("ck_ai_runs_context"),
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (failure_code IS NOT NULL)",
            name=op.f("ck_ai_runs_failure"),
        ),
        sa.CheckConstraint(
            "(status IN ('succeeded','empty')) = (result_hash IS NOT NULL)",
            name=op.f("ck_ai_runs_result"),
        ),
        sa.CheckConstraint(
            "purpose IN ('chat','applicant_review','applicant_recommendation')",
            name=op.f("ck_ai_runs_purpose"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','succeeded','empty','failed','canceled')",
            name=op.f("ck_ai_runs_status"),
        ),
        sa.CheckConstraint("attempt >= 1", name=op.f("ck_ai_runs_attempt")),
        sa.CheckConstraint(
            "deadline_at > created_at AND expires_at > deadline_at",
            name=op.f("ck_ai_runs_times"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name=op.f("fk_ai_runs_account_id_accounts"),
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            name=op.f("fk_ai_runs_application_id_applications"),
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["auth_session_id"],
            ["auth_sessions.auth_session_id"],
            name=op.f("fk_ai_runs_auth_session_id_auth_sessions"),
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.team_id"],
            name=op.f("fk_ai_runs_team_id_teams"),
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ai_run_id", name=op.f("pk_ai_runs")),
        sa.UniqueConstraint(
            "auth_session_id",
            "conversation_id",
            "client_message_id",
            name="uq_ai_runs_client_message",
        ),
    )
    op.create_index(
        "ix_ai_runs_account_created",
        "ai_runs",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_ai_runs_expires", "ai_runs", ["expires_at"], unique=False)
    op.create_index(
        "uq_ai_runs_pending_scope",
        "ai_runs",
        ["account_id", "scope_key"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ai_runs_pending_scope",
        table_name="ai_runs",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index("ix_ai_runs_expires", table_name="ai_runs")
    op.drop_index("ix_ai_runs_account_created", table_name="ai_runs")
    op.drop_table("ai_runs")
