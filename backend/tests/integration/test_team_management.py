"""모집 변경의 권한·버전·원자성과 잠금 대기 뒤 마감 검사를 검증한다."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from app.core.db.session import Database
from app.core.exceptions import AppError
from app.models.applications import Application, ApplicationEvent
from app.models.teams import Team, TeamMembership
from app.services import teams as management
from app.services.teams import close_recruitment, reopen_recruitment
from tests.integration.team_management_support import (
    NOW,
    prepare_team,
    seed_account,
    seed_application,
    seed_contest,
    seed_membership,
    seed_team,
)
from tests.integration.team_management_support import (
    management_database as management_database,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(management, "_utcnow", lambda: NOW)


async def test_closure_keeps_applications_and_members_and_noop_preserves_version(
    management_database: Database,
) -> None:
    database = management_database
    team_id, owner_id = await prepare_team(database)
    async with database.session() as session:
        team = await session.get(Team, team_id)
        assert team is not None
        applicant = await seed_account(session)
        application = await seed_application(session, team, applicant)
        await session.commit()
        application_id = application.application_id
    async with database.session() as session:
        closed = await close_recruitment(session, team_id, owner_id, expected_version=1)
        assert closed.version == "2"
        assert closed.recruitment_state == "closed"
        assert closed.closed_reason == "leader_closed"
        assert not closed.is_recruiting
    async with database.session() as session:
        unchanged = await close_recruitment(
            session, team_id, owner_id, expected_version=2
        )
        assert unchanged.version == "2"
    async with database.session() as session:
        team = await session.get(Team, team_id)
        assert team is not None
        assert team.updated_at == NOW
        saved_application = await session.get(Application, application_id)
        assert saved_application is not None and saved_application.status == "submitted"
        assert (
            await session.scalar(select(func.count()).select_from(TeamMembership)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationEvent))
            == 0
        )


async def test_old_version_is_rejected_even_when_already_closed(
    management_database: Database,
) -> None:
    team_id, owner_id = await prepare_team(management_database)
    async with management_database.session() as session:
        await close_recruitment(session, team_id, owner_id, expected_version=1)
    async with management_database.session() as session:
        with pytest.raises(AppError) as error:
            await close_recruitment(session, team_id, owner_id, expected_version=1)
        assert error.value.code == "VERSION_CONFLICT"


async def test_capacity_reason_is_preserved_and_returned_seat_needs_explicit_reopen(
    management_database: Database,
) -> None:
    database = management_database
    async with database.session() as session:
        leader = await seed_account(session)
        contest = await seed_contest(session)
        team = await seed_team(
            session,
            contest,
            leader,
            capacity=2,
            recruitment_state="closed",
            closed_reason="capacity_reached",
        )
        member = await seed_account(session)
        membership = await seed_membership(session, team, member)
        await session.commit()
        team_id, owner_id, membership_id = (
            team.team_id,
            leader.account_id,
            membership.team_membership_id,
        )
    async with database.session() as session:
        unchanged = await close_recruitment(
            session, team_id, owner_id, expected_version=1
        )
        assert unchanged.closed_reason == "capacity_reached"
        assert unchanged.version == "1"
        with pytest.raises(AppError) as error:
            await reopen_recruitment(session, team_id, owner_id, expected_version=1)
        assert error.value.code == "TEAM_FULL"
    async with database.session() as session:
        saved_membership = await session.get(TeamMembership, membership_id)
        assert saved_membership is not None
        saved_membership.ended_at = NOW + timedelta(seconds=1)
        saved_membership.end_reason = "application_canceled"
        await session.commit()
    async with database.session() as session:
        still_closed = await session.get(Team, team_id)
        assert still_closed is not None and still_closed.recruitment_state == "closed"
    async with database.session() as session:
        opened = await reopen_recruitment(
            session, team_id, owner_id, expected_version=1
        )
        assert (opened.version, opened.recruitment_state, opened.closed_reason) == (
            "2",
            "open",
            None,
        )
        assert opened.is_recruiting
    async with database.session() as session:
        noop = await reopen_recruitment(session, team_id, owner_id, expected_version=2)
        assert noop.version == "2"


@pytest.mark.parametrize("boundary", ["contest", "team"])
async def test_reopening_after_exact_deadline_fails_even_if_stored_open(
    management_database: Database, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    team_id, owner_id = await prepare_team(management_database)
    check_time = NOW + timedelta(days=30 if boundary == "contest" else 7)
    monkeypatch.setattr(management, "_utcnow", lambda: check_time)
    async with management_database.session() as session:
        with pytest.raises(AppError) as error:
            await reopen_recruitment(session, team_id, owner_id, expected_version=1)
        assert error.value.code == (
            "CONTEST_NOT_OPEN"
            if boundary == "contest"
            else "RECRUITMENT_DEADLINE_PASSED"
        )
    async with management_database.session() as session:
        team = await session.get(Team, team_id)
        assert team is not None
        assert team.version == 1
        assert team.recruitment_state == "open"


async def test_nonleader_cannot_change_recruitment(
    management_database: Database,
) -> None:
    team_id, _ = await prepare_team(management_database)
    async with management_database.session() as session:
        member = await seed_account(session)
        team = await session.get(Team, team_id)
        assert team is not None
        await seed_membership(session, team, member)
        await session.commit()
        member_id = member.account_id
    async with management_database.session() as session:
        with pytest.raises(AppError) as error:
            await close_recruitment(session, team_id, member_id, expected_version=1)
        assert error.value.status_code == 403


async def test_concurrent_commands_with_one_version_only_change_once(
    management_database: Database,
) -> None:
    team_id, owner_id = await prepare_team(management_database)

    async def close() -> str:
        async with management_database.session() as session:
            try:
                return (
                    await close_recruitment(
                        session, team_id, owner_id, expected_version=1
                    )
                ).version
            except AppError as error:
                return error.code

    assert sorted(await asyncio.gather(close(), close())) == ["2", "VERSION_CONFLICT"]


async def test_reopening_uses_time_after_waiting_for_the_team_lock(
    management_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    team_id, owner_id = await prepare_team(management_database)
    clock = [NOW]
    monkeypatch.setattr(management, "_utcnow", lambda: clock[0])

    async def reopen() -> str:
        async with management_database.session() as session:
            try:
                await reopen_recruitment(session, team_id, owner_id, expected_version=1)
                return "unexpected success"
            except AppError as error:
                return error.code

    async with management_database.session() as holding:
        await holding.scalar(
            select(Team).where(Team.team_id == team_id).with_for_update()
        )
        pending = asyncio.create_task(reopen())
        try:
            async with asyncio.timeout(5):
                async with management_database.engine.connect() as observer:
                    app_name = await observer.scalar(text("SHOW application_name"))
                    while True:
                        waiting = await observer.scalar(
                            text(
                                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE application_name = :name "
                                "AND wait_event_type = 'Lock')"
                            ),
                            {"name": app_name},
                        )
                        await observer.commit()
                        if waiting:
                            break
                        await asyncio.sleep(0.01)
            clock[0] = NOW + timedelta(days=7)
            await holding.commit()
            assert await pending == "RECRUITMENT_DEADLINE_PASSED"
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
