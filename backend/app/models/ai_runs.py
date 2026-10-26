"""대화 원문 없이 AI 실행의 소유권·시도·기한·근거 해시를 저장한다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.types import UUIDPrimaryKey


class AiRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('chat','applicant_review','applicant_recommendation')",
            name="ck_ai_runs_purpose",
        ),
        CheckConstraint(
            "status IN ('pending','succeeded','empty','failed','canceled')",
            name="ck_ai_runs_status",
        ),
        CheckConstraint("attempt >= 1", name="ck_ai_runs_attempt"),
        CheckConstraint(
            "(purpose = 'chat' AND conversation_id IS NOT NULL AND "
            "client_message_id IS NOT NULL AND team_id IS NULL AND "
            "application_id IS NULL) OR (purpose = 'applicant_review' AND "
            "conversation_id IS NULL AND client_message_id IS NULL AND "
            "team_id IS NOT NULL AND application_id IS NOT NULL) OR (purpose "
            "= 'applicant_recommendation' AND conversation_id IS NULL AND "
            "client_message_id IS NULL AND team_id IS NOT NULL AND "
            "application_id IS NULL)",
            name="ck_ai_runs_context",
        ),
        CheckConstraint(
            "(status IN ('succeeded','empty')) = (result_hash IS NOT NULL)",
            name="ck_ai_runs_result",
        ),
        CheckConstraint(
            "(status = 'failed') = (failure_code IS NOT NULL)",
            name="ck_ai_runs_failure",
        ),
        CheckConstraint(
            "deadline_at > created_at AND expires_at > deadline_at",
            name="ck_ai_runs_times",
        ),
        UniqueConstraint(
            "auth_session_id",
            "conversation_id",
            "client_message_id",
            name="uq_ai_runs_client_message",
        ),
        Index(
            "uq_ai_runs_pending_scope",
            "account_id",
            "scope_key",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_ai_runs_expires", "expires_at"),
        Index("ix_ai_runs_account_created", "account_id", "created_at"),
    )

    ai_run_id: Mapped[UUIDPrimaryKey]
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    auth_session_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "auth_sessions.auth_session_id", ondelete="RESTRICT", onupdate="RESTRICT"
        )
    )
    purpose: Mapped[str] = mapped_column(String(32))
    scope_key: Mapped[str] = mapped_column(String(90))
    conversation_id: Mapped[UUID | None]
    client_message_id: Mapped[UUID | None]
    team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.team_id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "applications.application_id", ondelete="RESTRICT", onupdate="RESTRICT"
        )
    )
    request_fingerprint: Mapped[str] = mapped_column(
        String(64), comment="정규화된 요청의 SHA-256. 입력 본문은 보존하지 않는다."
    )
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    failure_code: Mapped[str | None] = mapped_column(String(32))
    references: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        comment="권한 재검증용 리소스 ID·버전·해시. 프로필 전문과 답변을 넣지 않는다.",
    )
    selected_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    result_hash: Mapped[str | None] = mapped_column(
        String(64), comment="브라우저가 재전송한 결과의 위변조 확인용 SHA-256."
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
