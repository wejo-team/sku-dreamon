"""일반 AI 대화의 계정 소유권과 접수 입력·완성 답변을 보존한다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.types import UUIDPrimaryKey


class AiConversation(Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (
        CheckConstraint("updated_at >= created_at", name="ck_ai_conversations_times"),
        Index("ix_ai_conversations_account_created", "account_id", "created_at"),
    )

    ai_conversation_id: Mapped[UUIDPrimaryKey]
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AiMessage(Base):
    __tablename__ = "ai_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_ai_messages_role"),
        CheckConstraint("attempt >= 1", name="ck_ai_messages_attempt"),
        CheckConstraint(
            "char_length(content) BETWEEN 1 AND 12000 AND "
            "(role != 'user' OR char_length(content) <= 1000)",
            name="ck_ai_messages_content",
        ),
        CheckConstraint(
            "jsonb_typeof(source_references) = 'array' AND "
            "((role = 'user' AND model IS NULL AND attempt = 1 "
            "AND source_references = '[]'::jsonb) "
            "OR (role = 'assistant' AND model IS NOT NULL))",
            name="ck_ai_messages_metadata",
        ),
        UniqueConstraint("request_id", "role", name="uq_ai_messages_request_role"),
        UniqueConstraint(
            "ai_conversation_id",
            "client_message_id",
            "role",
            name="uq_ai_messages_conversation_client_role",
        ),
        Index(
            "ix_ai_messages_conversation_created", "ai_conversation_id", "created_at"
        ),
    )

    ai_message_id: Mapped[UUIDPrimaryKey]
    ai_conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "ai_conversations.ai_conversation_id",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        )
    )
    client_message_id: Mapped[UUID]
    # 실행 메타데이터 정리와 독립적으로 보존하므로 ai_runs FK를 두지 않는다.
    request_id: Mapped[UUID] = mapped_column(
        comment="원래 AI 실행 ID. ai_runs 삭제 뒤에도 유지한다."
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(
        Text, comment="접수한 사용자 입력 또는 생성 완료한 답변 원문."
    )
    attempt: Mapped[int] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(64))
    source_references: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        comment="답변의 근거 ID·버전·해시. 조회 API의 권한 검증을 대체하지 않는다.",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
