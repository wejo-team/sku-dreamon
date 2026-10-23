"""팀·지원·소속의 복합 참조와 중복 방어가 PostgreSQL DDL에 남는지 검사한다."""

from collections.abc import Callable
from typing import cast

from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from app.domains.applications.models import Application, ApplicationEvent
from app.domains.notifications.models import Notification
from app.domains.teams.models import Team, TeamMembership, TeamRecruitmentRole

DIALECT = cast(Callable[[], Dialect], postgresql.dialect)()


def test_postgresql_tables_keep_expected_storage_types() -> None:
    # 계정·공고의 실제 모델은 통합 검사에서 등록한다. 여기서는 이 도메인의
    # 컬럼·CHECK·UNIQUE DDL만 검사하며 참조 테이블 대역은 만들지 않는다.
    ddl = "\n".join(
        str(
            CreateTable(
                cast(Table, model.__table__), include_foreign_key_constraints=[]
            ).compile(dialect=DIALECT)
        )
        for model in (
            Team,
            TeamRecruitmentRole,
            Application,
            TeamMembership,
            ApplicationEvent,
            Notification,
        )
    )

    assert "target_capacity BIGINT NOT NULL" in ddl
    assert "request_fingerprint CHAR(64) NOT NULL" in ddl
    assert "occurred_at TIMESTAMP WITH TIME ZONE" in ddl
    assert "PRIMARY KEY (team_id, role_code)" in ddl
    assert "UNIQUE (application_id, application_version)" in ddl
    assert "UNIQUE (event_id, recipient_account_id)" in ddl


def test_partial_unique_indexes_allow_history_but_protect_current_state() -> None:
    indexes = {
        str(index.name): str(CreateIndex(index).compile(dialect=DIALECT))
        for model in (Application, TeamMembership)
        for index in cast(Table, model.__table__).indexes
    }

    assert "CREATE UNIQUE INDEX" in indexes["uq_applications_current"]
    assert (
        "WHERE status IN ('submitted', 'reviewing', 'selected')"
        in indexes["uq_applications_current"]
    )
    assert "CREATE UNIQUE INDEX" in indexes["uq_memberships_active_contest"]
    assert (
        "(account_id, contest_id) WHERE ended_at IS NULL"
        in indexes["uq_memberships_active_contest"]
    )


def test_composite_foreign_keys_preserve_application_and_cause_context() -> None:
    foreign_keys = {
        str(constraint.name): (
            tuple(constraint.column_keys),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for model in (Application, TeamMembership, ApplicationEvent)
        for constraint in cast(Table, model.__table__).foreign_key_constraints
    }

    assert foreign_keys["fk_memberships_application_context"] == (
        ("source_application_id", "team_id", "contest_id", "account_id"),
        (
            "applications.application_id",
            "applications.team_id",
            "applications.contest_id",
            "applications.applicant_account_id",
        ),
    )
    assert foreign_keys["fk_application_events_cause"] == (
        ("cause_event_id", "contest_id", "applicant_account_id"),
        (
            "application_events.application_event_id",
            "application_events.contest_id",
            "application_events.applicant_account_id",
        ),
    )


def test_domain_foreign_keys_never_cascade_business_history() -> None:
    for model in (
        Team,
        TeamRecruitmentRole,
        Application,
        TeamMembership,
        ApplicationEvent,
        Notification,
    ):
        for constraint in cast(Table, model.__table__).foreign_key_constraints:
            assert constraint.ondelete == "RESTRICT"
            assert constraint.onupdate == "RESTRICT"
