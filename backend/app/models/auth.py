"""불변 계정 식별자와 해시로 검증하는 로그인 세션을 저장한다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.mixins import CreatedAtMixin
from app.core.db.types import UUIDPrimaryKey


class Account(CreatedAtMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("login_id_normalized", name="uq_accounts_login_id"),
        CheckConstraint(
            "login_id_normalized COLLATE \"C\" ~ '^[a-z0-9]{4,24}$'",
            name="ck_accounts_login_id",
        ),
        CheckConstraint("password_hash <> ''", name="ck_accounts_password_hash"),
        CheckConstraint(
            "school_email_verified_at IS NULL OR school_email IS NOT NULL",
            name="ck_accounts_school_email_verified",
        ),
    )

    account_id: Mapped[UUIDPrimaryKey]
    login_id_normalized: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(Text)
    credentials_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    school_email: Mapped[str | None] = mapped_column(String(320))
    school_email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        CheckConstraint(
            "octet_length(token_hash) = 32", name="ck_auth_sessions_token_hash"
        ),
        CheckConstraint(
            "last_seen_at >= created_at AND expires_at > created_at "
            "AND (revoked_at IS NULL OR revoked_at >= created_at)",
            name="ck_auth_sessions_times",
        ),
        Index("ix_auth_sessions_account", "account_id"),
        Index("ix_auth_sessions_expires", "expires_at"),
    )

    auth_session_id: Mapped[UUIDPrimaryKey]
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "accounts.account_id",
            name="fk_auth_sessions_account",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        )
    )
    # 발급 서비스가 동일한 시각을 넣어 유휴·절대 만료 계산 기준을 고정한다.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
