"""공고 원문·적용 일정과 대상·분야 연결의 저장 제약을 정의한다."""

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.mixins import CreatedAtMixin, UpdatedAtMixin
from app.core.db.types import UUIDPrimaryKey


class Contest(CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "contests"
    __table_args__ = (
        CheckConstraint(
            "title ~ '[^[:space:]]' AND organizer_name ~ '[^[:space:]]' "
            "AND eligibility_text ~ '[^[:space:]]' AND official_url ~ '[^[:space:]]'",
            name="ck_contests_required_text",
        ),
        CheckConstraint(
            "(member_limit_kind = 'range' AND min_members IS NOT NULL "
            "AND max_members IS NOT NULL AND min_members > 0 "
            "AND max_members >= min_members) OR "
            "(member_limit_kind = 'unlimited' AND max_members IS NULL "
            "AND (min_members IS NULL OR min_members > 0)) OR "
            "(member_limit_kind = 'unknown' AND min_members IS NULL "
            "AND max_members IS NULL)",
            name="ck_contests_member_limit",
        ),
        CheckConstraint(
            "registration_opens_at < registration_closes_at",
            name="ck_contests_period",
        ),
        CheckConstraint(
            "close_time_assumed = (close_source_time IS NULL) "
            "AND close_timezone_assumed = (close_source_timezone IS NULL) "
            "AND open_timezone_assumed = (open_source_timezone IS NULL)",
            name="ck_contests_deadline_assumptions",
        ),
        CheckConstraint("version > 0", name="ck_contests_version"),
        Index("ix_contests_created", text("created_at DESC"), text("contest_id DESC")),
        Index("ix_contests_closes", "registration_closes_at", "contest_id"),
    )

    contest_id: Mapped[UUIDPrimaryKey]
    title: Mapped[str] = mapped_column(Text)
    organizer_name: Mapped[str] = mapped_column(Text)
    official_url: Mapped[str] = mapped_column(Text)
    eligibility_text: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    submission_details: Mapped[str | None] = mapped_column(Text)
    awards: Mapped[str | None] = mapped_column(Text)
    contact_info: Mapped[str | None] = mapped_column(Text)
    poster_url: Mapped[str | None] = mapped_column(Text)
    member_limit_kind: Mapped[str] = mapped_column(String(16))
    min_members: Mapped[int | None] = mapped_column(BigInteger)
    max_members: Mapped[int | None] = mapped_column(BigInteger)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    registration_opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open_source_date: Mapped[date] = mapped_column(Date)
    open_source_time: Mapped[time | None] = mapped_column(Time(timezone=False))
    open_source_timezone: Mapped[str | None] = mapped_column(Text)
    open_effective_timezone: Mapped[str] = mapped_column(Text)
    open_timezone_assumed: Mapped[bool] = mapped_column(Boolean)
    close_source_date: Mapped[date] = mapped_column(Date)
    close_source_time: Mapped[time | None] = mapped_column(Time(timezone=False))
    close_source_timezone: Mapped[str | None] = mapped_column(Text)
    close_effective_timezone: Mapped[str] = mapped_column(Text)
    close_time_assumed: Mapped[bool] = mapped_column(Boolean)
    close_timezone_assumed: Mapped[bool] = mapped_column(Boolean)


class ContestAudience(Base):
    __tablename__ = "contest_audiences"
    __table_args__ = (
        CheckConstraint(
            "audience_code IN ('student', 'general', 'unrestricted', 'unknown')",
            name="ck_contest_audiences_code",
        ),
    )

    contest_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "contests.contest_id",
            name="fk_contest_audiences_contest",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    audience_code: Mapped[str] = mapped_column(String(16), primary_key=True)


class ContestField(Base):
    __tablename__ = "contest_fields"
    __table_args__ = (Index("ix_contest_fields_field", "field_code", "contest_id"),)

    contest_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "contests.contest_id",
            name="fk_contest_fields_contest",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    field_code: Mapped[str] = mapped_column(String(64), primary_key=True)
