"""팀·지원·소속·발생 건·알림의 무결성 제약을 생성한다.

리비전 ID: 20261024_05
이전 리비전: 통합 시 선행 도메인 migration과 연결한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_05"
down_revision: str | Sequence[str] | None = "20261024_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("contest_id", sa.Uuid(), nullable=False),
        sa.Column("leader_account_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("introduction", sa.Text(), nullable=False),
        sa.Column("target_capacity", sa.BigInteger(), nullable=False),
        sa.Column("recruitment_state", sa.String(length=16), nullable=False),
        sa.Column("closed_reason", sa.String(length=32), nullable=True),
        sa.Column("recruitment_closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_source_date", sa.Date(), nullable=False),
        sa.Column("deadline_source_time", sa.Time(), nullable=True),
        sa.Column("deadline_source_timezone", sa.Text(), nullable=True),
        sa.Column("deadline_effective_timezone", sa.Text(), nullable=False),
        sa.Column("deadline_time_assumed", sa.Boolean(), nullable=False),
        sa.Column("deadline_timezone_assumed", sa.Boolean(), nullable=False),
        sa.Column(
            "version", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(recruitment_state = 'open' AND closed_reason IS NULL) OR "
            "(recruitment_state = 'closed' AND closed_reason IS NOT NULL AND "
            "closed_reason IN ('leader_closed', 'capacity_reached'))",
            name=op.f("ck_teams_closed_reason"),
        ),
        sa.CheckConstraint(
            "name ~ '[^[:space:]]' AND introduction ~ '[^[:space:]]'",
            name=op.f("ck_teams_text"),
        ),
        sa.CheckConstraint(
            "recruitment_state IN ('open', 'closed')",
            name=op.f("ck_teams_recruitment_state"),
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_teams_request_fingerprint"),
        ),
        sa.CheckConstraint(
            "deadline_time_assumed = (deadline_source_time IS NULL) AND "
            "deadline_timezone_assumed = (deadline_source_timezone IS NULL)",
            name=op.f("ck_teams_deadline_assumptions"),
        ),
        sa.CheckConstraint("target_capacity > 0", name=op.f("ck_teams_capacity")),
        sa.CheckConstraint("version > 0", name=op.f("ck_teams_version")),
        sa.ForeignKeyConstraint(
            ["contest_id"],
            ["contests.contest_id"],
            name="fk_teams_contest",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["leader_account_id"],
            ["accounts.account_id"],
            name="fk_teams_leader",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("team_id", name=op.f("pk_teams")),
        sa.UniqueConstraint("leader_account_id", "request_id", name="uq_teams_request"),
        sa.UniqueConstraint("team_id", "contest_id", name="uq_teams_id_contest"),
    )
    op.create_index(
        "ix_teams_contest_created",
        "teams",
        [
            "contest_id",
            sa.literal_column("created_at DESC"),
            sa.literal_column("team_id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_teams_created",
        "teams",
        [sa.literal_column("created_at DESC"), sa.literal_column("team_id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_teams_leader", "teams", ["leader_account_id", "team_id"], unique=False
    )
    op.create_table(
        "team_recruitment_roles",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.team_id"],
            name="fk_team_recruitment_roles_team",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "team_id", "role_code", name=op.f("pk_team_recruitment_roles")
        ),
    )
    op.create_index(
        "ix_team_recruitment_roles_role",
        "team_recruitment_roles",
        ["role_code", "team_id"],
        unique=False,
    )
    op.create_table(
        "applications",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("contest_id", sa.Uuid(), nullable=False),
        sa.Column("applicant_account_id", sa.Uuid(), nullable=False),
        sa.Column("applied_role_code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'submitted'"),
            nullable=False,
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "version", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "message IS NULL OR message ~ '[^[:space:]]'",
            name=op.f("ck_applications_message"),
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_applications_request_fingerprint"),
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'reviewing', 'selected', 'rejected', "
            "'canceled', 'discarded')",
            name=op.f("ck_applications_status"),
        ),
        sa.CheckConstraint(
            "status_changed_at >= submitted_at AND version > 0",
            name=op.f("ck_applications_time_version"),
        ),
        sa.ForeignKeyConstraint(
            ["applicant_account_id"],
            ["accounts.account_id"],
            name="fk_applications_account",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "contest_id"],
            ["teams.team_id", "teams.contest_id"],
            name="fk_applications_team_context",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("application_id", name=op.f("pk_applications")),
        sa.UniqueConstraint(
            "applicant_account_id", "request_id", name="uq_applications_request"
        ),
        sa.UniqueConstraint(
            "application_id",
            "team_id",
            "contest_id",
            "applicant_account_id",
            name="uq_applications_context",
        ),
    )
    op.create_index(
        "ix_applications_account",
        "applications",
        [
            "applicant_account_id",
            sa.literal_column("submitted_at DESC"),
            sa.literal_column("application_id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_applications_pending_contest",
        "applications",
        ["applicant_account_id", "contest_id", "application_id"],
        unique=False,
        postgresql_where=sa.text("status IN ('submitted', 'reviewing')"),
    )
    op.create_index(
        "ix_applications_rejected_history",
        "applications",
        ["team_id", "applicant_account_id"],
        unique=False,
        postgresql_where=sa.text("status = 'rejected'"),
    )
    op.create_index(
        "ix_applications_role", "applications", ["applied_role_code"], unique=False
    )
    op.create_index(
        "ix_applications_team_status",
        "applications",
        [
            "team_id",
            "status",
            sa.literal_column("submitted_at DESC"),
            sa.literal_column("application_id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "uq_applications_current",
        "applications",
        ["team_id", "applicant_account_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('submitted', 'reviewing', 'selected')"),
    )
    op.create_table(
        "team_memberships",
        sa.Column("team_membership_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("contest_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("source_application_id", sa.Uuid(), nullable=True),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "(ended_at IS NULL AND end_reason IS NULL) OR (ended_at IS NOT NULL "
            "AND ended_at >= joined_at AND end_reason IS NOT NULL AND end_reason "
            "= 'application_canceled')",
            name=op.f("ck_memberships_end"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.account_id"],
            name="fk_memberships_account",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_application_id", "team_id", "contest_id", "account_id"],
            [
                "applications.application_id",
                "applications.team_id",
                "applications.contest_id",
                "applications.applicant_account_id",
            ],
            name="fk_memberships_application_context",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id", "contest_id"],
            ["teams.team_id", "teams.contest_id"],
            name="fk_memberships_team_context",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("team_membership_id", name=op.f("pk_team_memberships")),
        sa.UniqueConstraint(
            "source_application_id", name="uq_memberships_source_application"
        ),
        sa.UniqueConstraint(
            "team_membership_id",
            "contest_id",
            "account_id",
            name="uq_memberships_cause_context",
        ),
    )
    op.create_index(
        "ix_memberships_account_history",
        "team_memberships",
        [
            "account_id",
            sa.literal_column("joined_at DESC"),
            sa.literal_column("team_membership_id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_memberships_team_active",
        "team_memberships",
        ["team_id", "account_id"],
        unique=False,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "ix_memberships_team_history",
        "team_memberships",
        ["team_id", "joined_at", "team_membership_id"],
        unique=False,
    )
    op.create_index(
        "uq_memberships_active_contest",
        "team_memberships",
        ["account_id", "contest_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_table(
        "application_events",
        sa.Column("application_event_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("contest_id", sa.Uuid(), nullable=False),
        sa.Column("applicant_account_id", sa.Uuid(), nullable=False),
        sa.Column("application_version", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("actor_account_id", sa.Uuid(), nullable=True),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("cause_event_id", sa.Uuid(), nullable=True),
        sa.Column("cause_membership_id", sa.Uuid(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(reason_code = 'selected_elsewhere' AND cause_event_id IS NOT NULL "
            "AND cause_membership_id IS NULL AND actor_account_id IS NULL) OR "
            "(reason_code = 'team_created_elsewhere' AND cause_membership_id IS "
            "NOT NULL AND cause_event_id IS NULL AND actor_account_id IS NULL) "
            "OR (reason_code NOT IN ('selected_elsewhere', "
            "'team_created_elsewhere') AND cause_event_id IS NULL AND "
            "cause_membership_id IS NULL AND actor_account_id IS NOT NULL)",
            name=op.f("ck_application_events_cause"),
        ),
        sa.CheckConstraint(
            "(reason_code = 'submitted' AND from_status IS NULL AND to_status = "
            "'submitted' AND application_version = 1) OR (application_version > "
            "1 AND from_status IS NOT NULL AND ((reason_code = 'selected' AND "
            "from_status IN ('submitted', 'reviewing') AND to_status = "
            "'selected') OR (reason_code = 'canceled' AND from_status IN "
            "('submitted', 'reviewing', 'selected') AND to_status = 'canceled') "
            "OR (reason_code IN ('selected_elsewhere', 'team_created_elsewhere') "
            "AND from_status IN ('submitted', 'reviewing') AND to_status = "
            "'discarded') OR (reason_code = 'reviewing_started' AND from_status "
            "= 'submitted' AND to_status = 'reviewing') OR (reason_code = "
            "'rejected' AND from_status IN ('submitted', 'reviewing') AND "
            "to_status = 'rejected')))",
            name=op.f("ck_application_events_transition"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_account_id"],
            ["accounts.account_id"],
            name="fk_application_events_actor",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["application_id", "team_id", "contest_id", "applicant_account_id"],
            [
                "applications.application_id",
                "applications.team_id",
                "applications.contest_id",
                "applications.applicant_account_id",
            ],
            name="fk_application_events_application",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cause_event_id", "contest_id", "applicant_account_id"],
            [
                "application_events.application_event_id",
                "application_events.contest_id",
                "application_events.applicant_account_id",
            ],
            name="fk_application_events_cause",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["cause_membership_id", "contest_id", "applicant_account_id"],
            [
                "team_memberships.team_membership_id",
                "team_memberships.contest_id",
                "team_memberships.account_id",
            ],
            name="fk_application_events_cause_membership",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint(
            "application_event_id", name=op.f("pk_application_events")
        ),
        sa.UniqueConstraint(
            "application_event_id",
            "contest_id",
            "applicant_account_id",
            name="uq_application_events_cause_context",
        ),
        sa.UniqueConstraint(
            "application_id",
            "application_version",
            name="uq_application_events_version",
        ),
    )
    op.create_index(
        "ix_application_events_actor",
        "application_events",
        ["actor_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_events_cause",
        "application_events",
        ["cause_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_events_cause_membership",
        "application_events",
        ["cause_membership_id"],
        unique=False,
    )
    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('application_status_changed', 'new_application')",
            name=op.f("ck_notifications_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["application_events.application_event_id"],
            name=op.f("fk_notifications_event_id_application_events"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_account_id"],
            ["accounts.account_id"],
            name=op.f("fk_notifications_recipient_account_id_accounts"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("notification_id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "event_id", "recipient_account_id", name="uq_notifications_event_recipient"
        ),
    )
    op.create_index(
        "ix_notifications_recipient",
        "notifications",
        ["recipient_account_id", "event_id", "notification_id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_unread",
        "notifications",
        ["recipient_account_id", "event_id", "notification_id"],
        unique=False,
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("application_events")
    op.drop_table("team_memberships")
    op.drop_table("applications")
    op.drop_table("team_recruitment_roles")
    op.drop_table("teams")
