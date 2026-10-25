"""상태 발생 건·수신자별 알림의 중복을 방지하고 읽음 시각을 저장한다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.types import UUIDPrimaryKey


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "recipient_account_id", name="uq_notifications_event_recipient"
        ),
        CheckConstraint(
            "kind IN ('application_status_changed', 'new_application')",
            name="ck_notifications_kind",
        ),
        Index(
            "ix_notifications_recipient",
            "recipient_account_id",
            "event_id",
            "notification_id",
        ),
        Index(
            "ix_notifications_unread",
            "recipient_account_id",
            "event_id",
            "notification_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    notification_id: Mapped[UUIDPrimaryKey]
    event_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "application_events.application_event_id",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    recipient_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("accounts.account_id", ondelete="RESTRICT", onupdate="RESTRICT"),
    )
    kind: Mapped[str] = mapped_column(String(32))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
