"""지원 시도와 상태 변경 사건의 문맥·유일성·허용 전이를 저장한다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.types import UUIDPrimaryKey


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "contest_id"],
            ["teams.team_id", "teams.contest_id"],
            name="fk_applications_team_context",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "applicant_account_id", "request_id", name="uq_applications_request"
        ),
        UniqueConstraint(
            "application_id",
            "team_id",
            "contest_id",
            "applicant_account_id",
            name="uq_applications_context",
        ),
        CheckConstraint(
            "status IN ('submitted', 'reviewing', 'selected', 'rejected', "
            "'canceled', 'discarded')",
            name="ck_applications_status",
        ),
        CheckConstraint(
            "message IS NULL OR message ~ '[^[:space:]]'",
            name="ck_applications_message",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_applications_request_fingerprint",
        ),
        CheckConstraint(
            "status_changed_at >= submitted_at AND version > 0",
            name="ck_applications_time_version",
        ),
        Index(
            "uq_applications_current",
            "team_id",
            "applicant_account_id",
            unique=True,
            postgresql_where=text("status IN ('submitted', 'reviewing', 'selected')"),
        ),
        Index(
            "ix_applications_team_status",
            "team_id",
            "status",
            text("submitted_at DESC"),
            text("application_id DESC"),
        ),
        Index(
            "ix_applications_account",
            "applicant_account_id",
            text("submitted_at DESC"),
            text("application_id DESC"),
        ),
        Index(
            "ix_applications_pending_contest",
            "applicant_account_id",
            "contest_id",
            "application_id",
            postgresql_where=text("status IN ('submitted', 'reviewing')"),
        ),
        Index(
            "ix_applications_rejected_history",
            "team_id",
            "applicant_account_id",
            postgresql_where=text("status = 'rejected'"),
        ),
        Index("ix_applications_role", "applied_role_code"),
    )

    application_id: Mapped[UUIDPrimaryKey]
    request_id: Mapped[UUID]
    request_fingerprint: Mapped[str] = mapped_column(CHAR(64))
    team_id: Mapped[UUID]
    contest_id: Mapped[UUID]
    applicant_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "accounts.account_id",
            name="fk_applications_account",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    applied_role_code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'submitted'"))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    version: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))


class ApplicationEvent(Base):
    """현재 상태와 구분하여 성공한 상태 변경의 원인과 문맥을 보존한다."""

    __tablename__ = "application_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["application_id", "team_id", "contest_id", "applicant_account_id"],
            [
                "applications.application_id",
                "applications.team_id",
                "applications.contest_id",
                "applications.applicant_account_id",
            ],
            name="fk_application_events_application",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["cause_event_id", "contest_id", "applicant_account_id"],
            [
                "application_events.application_event_id",
                "application_events.contest_id",
                "application_events.applicant_account_id",
            ],
            name="fk_application_events_cause",
            match="SIMPLE",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["cause_membership_id", "contest_id", "applicant_account_id"],
            [
                "team_memberships.team_membership_id",
                "team_memberships.contest_id",
                "team_memberships.account_id",
            ],
            name="fk_application_events_cause_membership",
            match="SIMPLE",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "application_id",
            "application_version",
            name="uq_application_events_version",
        ),
        UniqueConstraint(
            "application_event_id",
            "contest_id",
            "applicant_account_id",
            name="uq_application_events_cause_context",
        ),
        CheckConstraint(
            "(reason_code = 'submitted' AND from_status IS NULL AND "
            "to_status = 'submitted' AND application_version = 1) OR "
            "(application_version > 1 AND from_status IS NOT NULL AND ("
            "(reason_code = 'selected' AND from_status IN ('submitted', 'reviewing') "
            "AND to_status = 'selected') OR "
            "(reason_code = 'canceled' AND from_status IN ('submitted', 'reviewing', "
            "'selected') AND to_status = 'canceled') OR "
            "(reason_code IN ('selected_elsewhere', 'team_created_elsewhere') "
            "AND from_status IN ('submitted', 'reviewing') "
            "AND to_status = 'discarded') OR "
            "(reason_code = 'reviewing_started' AND from_status = 'submitted' "
            "AND to_status = 'reviewing') OR "
            "(reason_code = 'rejected' AND from_status IN ('submitted', 'reviewing') "
            "AND to_status = 'rejected')))",
            name="ck_application_events_transition",
        ),
        CheckConstraint(
            "(reason_code = 'selected_elsewhere' AND cause_event_id IS NOT NULL AND "
            "cause_membership_id IS NULL AND actor_account_id IS NULL) OR "
            "(reason_code = 'team_created_elsewhere' "
            "AND cause_membership_id IS NOT NULL "
            "AND cause_event_id IS NULL AND actor_account_id IS NULL) OR "
            "(reason_code NOT IN ('selected_elsewhere', 'team_created_elsewhere') AND "
            "cause_event_id IS NULL AND cause_membership_id IS NULL AND "
            "actor_account_id IS NOT NULL)",
            name="ck_application_events_cause",
        ),
        Index("ix_application_events_cause", "cause_event_id"),
        Index("ix_application_events_cause_membership", "cause_membership_id"),
        Index("ix_application_events_actor", "actor_account_id"),
    )

    application_event_id: Mapped[UUIDPrimaryKey]
    application_id: Mapped[UUID]
    team_id: Mapped[UUID]
    contest_id: Mapped[UUID]
    applicant_account_id: Mapped[UUID]
    application_version: Mapped[int] = mapped_column(BigInteger)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    actor_account_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "accounts.account_id",
            name="fk_application_events_actor",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    reason_code: Mapped[str] = mapped_column(String(32))
    cause_event_id: Mapped[UUID | None]
    cause_membership_id: Mapped[UUID | None]
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
