"""일반 AI 대화와 메시지 원문 저장을 추가한다.

DB 스키마 변경과 복원을 정의한다.

리비전 ID: 20261025_08
이전 리비전: 20261025_07
생성 시각: 2026-10-25 18:28:28.524555
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261025_08"
down_revision: str | Sequence[str] | None = "20261025_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("ai_conversation_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f("ck_ai_conversations_times")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name=op.f("fk_ai_conversations_account_id_accounts"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ai_conversation_id", name=op.f("pk_ai_conversations")),
    )
    op.create_index(
        "ix_ai_conversations_account_created",
        "ai_conversations",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "ai_messages",
        sa.Column("ai_message_id", sa.Uuid(), nullable=False),
        sa.Column("ai_conversation_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column(
            "request_id",
            sa.Uuid(),
            nullable=False,
            comment="원래 AI 실행 ID. ai_runs 삭제 뒤에도 유지한다.",
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="접수한 사용자 입력 또는 생성 완료한 답변 원문.",
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column(
            "source_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="답변의 근거 ID·버전·해시. 조회 API의 권한 검증을 대체하지 않는다.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(content) BETWEEN 1 AND 12000 AND "
            "(role != 'user' OR char_length(content) <= 1000)",
            name=op.f("ck_ai_messages_content"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_references) = 'array' AND "
            "((role = 'user' AND model IS NULL AND attempt = 1 "
            "AND source_references = '[]'::jsonb) "
            "OR (role = 'assistant' AND model IS NOT NULL))",
            name=op.f("ck_ai_messages_metadata"),
        ),
        sa.CheckConstraint(
            "role IN ('user','assistant')", name=op.f("ck_ai_messages_role")
        ),
        sa.CheckConstraint("attempt >= 1", name=op.f("ck_ai_messages_attempt")),
        sa.ForeignKeyConstraint(
            ["ai_conversation_id"],
            ["ai_conversations.ai_conversation_id"],
            name=op.f("fk_ai_messages_ai_conversation_id_ai_conversations"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ai_message_id", name=op.f("pk_ai_messages")),
        sa.UniqueConstraint(
            "ai_conversation_id",
            "client_message_id",
            "role",
            name="uq_ai_messages_conversation_client_role",
        ),
        sa.UniqueConstraint("request_id", "role", name="uq_ai_messages_request_role"),
    )
    op.create_index(
        "ix_ai_messages_conversation_created",
        "ai_messages",
        ["ai_conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_messages_conversation_created", table_name="ai_messages")
    op.drop_table("ai_messages")
    op.drop_index("ix_ai_conversations_account_created", table_name="ai_conversations")
    op.drop_table("ai_conversations")
