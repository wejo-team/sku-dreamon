"""팀·모집 역할·소속 이력과 공모전별 현재 소속 제약을 정의한다."""

from datetime import date, datetime, time
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
from app.core.db.mixins import CreatedAtMixin, UpdatedAtMixin
from app.core.db.types import UUIDPrimaryKey


class Team(CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("leader_account_id", "request_id", name="uq_teams_request"),
        UniqueConstraint("team_id", "contest_id", name="uq_teams_id_contest"),
        CheckConstraint(
            "name ~ '[^[:space:]]' AND introduction ~ '[^[:space:]]'",
            name="ck_teams_text",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_teams_request_fingerprint",
        ),
        CheckConstraint("target_capacity > 0", name="ck_teams_capacity"),
        CheckConstraint(
            "recruitment_state IN ('open', 'closed')",
            name="ck_teams_recruitment_state",
        ),
        CheckConstraint(
            "(recruitment_state = 'open' AND closed_reason IS NULL) OR "
            "(recruitment_state = 'closed' AND closed_reason IS NOT NULL AND "
            "closed_reason IN ('leader_closed', 'capacity_reached'))",
            name="ck_teams_closed_reason",
        ),
        CheckConstraint(
            "deadline_time_assumed = (deadline_source_time IS NULL) AND "
            "deadline_timezone_assumed = (deadline_source_timezone IS NULL)",
            name="ck_teams_deadline_assumptions",
        ),
        CheckConstraint("version > 0", name="ck_teams_version"),
        Index(
            "ix_teams_contest_created",
            "contest_id",
            text("created_at DESC"),
            text("team_id DESC"),
        ),
        Index("ix_teams_created", text("created_at DESC"), text("team_id DESC")),
        Index("ix_teams_leader", "leader_account_id", "team_id"),
    )

    team_id: Mapped[UUIDPrimaryKey]
    request_id: Mapped[UUID]
    request_fingerprint: Mapped[str] = mapped_column(CHAR(64))
    contest_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "contests.contest_id",
            name="fk_teams_contest",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    leader_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "accounts.account_id",
            name="fk_teams_leader",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    name: Mapped[str] = mapped_column(Text)
    introduction: Mapped[str] = mapped_column(Text)
    target_capacity: Mapped[int] = mapped_column(BigInteger)
    recruitment_state: Mapped[str] = mapped_column(String(16))
    closed_reason: Mapped[str | None] = mapped_column(String(32))
    recruitment_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_source_date: Mapped[date]
    deadline_source_time: Mapped[time | None]
    deadline_source_timezone: Mapped[str | None] = mapped_column(Text)
    deadline_effective_timezone: Mapped[str] = mapped_column(Text)
    deadline_time_assumed: Mapped[bool]
    deadline_timezone_assumed: Mapped[bool]
    version: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))


class TeamRecruitmentRole(Base):
    __tablename__ = "team_recruitment_roles"
    __table_args__ = (Index("ix_team_recruitment_roles_role", "role_code", "team_id"),)

    team_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "teams.team_id",
            name="fk_team_recruitment_roles_team",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    role_code: Mapped[str] = mapped_column(String(64), primary_key=True)


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "contest_id"],
            ["teams.team_id", "teams.contest_id"],
            name="fk_memberships_team_context",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_application_id", "team_id", "contest_id", "account_id"],
            [
                "applications.application_id",
                "applications.team_id",
                "applications.contest_id",
                "applications.applicant_account_id",
            ],
            name="fk_memberships_application_context",
            match="SIMPLE",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "source_application_id", name="uq_memberships_source_application"
        ),
        UniqueConstraint(
            "team_membership_id",
            "contest_id",
            "account_id",
            name="uq_memberships_cause_context",
        ),
        CheckConstraint(
            "(ended_at IS NULL AND end_reason IS NULL) OR "
            "(ended_at IS NOT NULL AND ended_at >= joined_at AND "
            "end_reason IS NOT NULL AND end_reason = 'application_canceled')",
            name="ck_memberships_end",
        ),
        Index(
            "uq_memberships_active_contest",
            "account_id",
            "contest_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        Index(
            "ix_memberships_team_active",
            "team_id",
            "account_id",
            postgresql_where=text("ended_at IS NULL"),
        ),
        Index(
            "ix_memberships_team_history", "team_id", "joined_at", "team_membership_id"
        ),
        Index(
            "ix_memberships_account_history",
            "account_id",
            text("joined_at DESC"),
            text("team_membership_id DESC"),
        ),
    )

    team_membership_id: Mapped[UUIDPrimaryKey]
    team_id: Mapped[UUID]
    contest_id: Mapped[UUID]
    account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "accounts.account_id",
            name="fk_memberships_account",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    source_application_id: Mapped[UUID | None]
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(32))
