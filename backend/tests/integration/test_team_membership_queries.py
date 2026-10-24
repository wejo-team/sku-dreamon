"""현재 소속·팀 공간 권한과 페이지 및 프로필 읽기 스냅샷을 검증한다."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, event, select, text, update
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.util import await_only

from app.core import demo_data as manifest
from app.core.db.session import Database
from app.core.exceptions import AppError
from app.models.profiles import Profile
from app.models.teams import TeamMembership
from app.services.team_memberships import get_team_space, list_workspace_teams
from tests.integration.team_management_support import (
    NOW,
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


async def test_workspace_uses_only_current_memberships_and_stable_order(
    management_database: Database,
) -> None:
    database = management_database
    async with database.session() as session:
        viewer = await seed_account(session)
        leader = await seed_account(session)
        outsider = await seed_account(session)
        own_team = await seed_team(session, await seed_contest(session), viewer)
        joined_teams = [
            await seed_team(session, await seed_contest(session), leader)
            for _ in range(2)
        ]
        memberships = [
            await seed_membership(
                session, team, viewer, joined_at=NOW + timedelta(seconds=1)
            )
            for team in joined_teams
        ]
        memberships[0].team_membership_id = UUID(int=1)
        memberships[1].team_membership_id = UUID(int=2)
        ended_team = await seed_team(session, await seed_contest(session), leader)
        await seed_membership(
            session, ended_team, viewer, ended_at=NOW + timedelta(seconds=1)
        )
        pending_team = await seed_team(session, await seed_contest(session), leader)
        await seed_application(session, pending_team, viewer)
        await seed_application(session, own_team, outsider)
        await session.commit()

    async with database.session() as session:
        first = await list_workspace_teams(session, viewer.account_id, page_size=1)
    async with database.session() as session:
        last = await list_workspace_teams(
            session, viewer.account_id, page=99, page_size=1
        )
    async with database.session() as session:
        empty = await list_workspace_teams(session, outsider.account_id, page=99)

    assert first.pagination.total == 3
    assert first.pagination.total_pages == 3
    assert first.data[0].membership_id == UUID(int=2)
    assert first.data[0].team.id == joined_teams[1].team_id
    assert first.data[0].membership_role == "member"
    assert first.data[0].role_code == "development"
    assert first.data[0].pending_application_count is None
    assert first.data[0].team.member_count == 2
    assert last.pagination.page == 3
    assert last.data[0].team.id == own_team.team_id
    assert last.data[0].membership_role == "leader"
    assert last.data[0].role_code is None
    assert last.data[0].pending_application_count == 1
    assert empty.data == []
    assert empty.pagination.page == 1
    assert empty.pagination.total == 0
    assert empty.pagination.total_pages == 0


async def test_space_separates_membership_names_demo_flags_and_full_profiles(
    management_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = management_database
    async with database.session() as session:
        leader = await seed_account(session, real_name="팀장")
        viewer = await seed_account(session, real_name="본인")
        private_member = await seed_account(session, real_name="비공개 팀원")
        public_member = await seed_account(
            session, real_name="공개 팀원", is_public=True
        )
        team = await seed_team(session, await seed_contest(session), leader, capacity=5)
        for account in (viewer, private_member, public_member):
            await seed_membership(session, team, account)
        await session.commit()
    monkeypatch.setattr(manifest, "ACCOUNT_IDS", frozenset({private_member.account_id}))

    async with database.session() as session:
        result = await get_team_space(session, team.team_id, viewer.account_id)

    members = {member.account_id: member for member in result.members}
    assert result.viewer_role == "member"
    assert result.pending_application_count is None
    assert result.team.member_count == 4
    own_profile = members[viewer.account_id].profile
    assert own_profile is not None
    assert own_profile.account_id == viewer.account_id
    assert members[public_member.account_id].profile is not None
    assert members[leader.account_id].profile is None
    hidden = members[private_member.account_id]
    assert hidden.real_name == "비공개 팀원"
    assert hidden.is_demo
    assert hidden.profile is None
    assert "private-portfolio" not in hidden.model_dump_json()
    assert "experienceBody" not in hidden.model_dump_json()


async def test_leader_profile_exception_requires_an_application_in_this_team(
    management_database: Database,
) -> None:
    database = management_database
    async with database.session() as session:
        leader = await seed_account(session)
        applicant = await seed_account(session, real_name="과거 지원자")
        unrelated = await seed_account(session, real_name="미지원자")
        team = await seed_team(session, await seed_contest(session), leader, capacity=5)
        await seed_application(session, team, applicant, status="rejected")
        # 소속이 존재한다는 사실만으로 팀장의 비공개 열람 권한을 추정하지 않는다.
        session.add_all(
            [
                TeamMembership(
                    team_id=team.team_id,
                    contest_id=team.contest_id,
                    account_id=account.account_id,
                    source_application_id=None,
                    joined_at=NOW,
                )
                for account in (applicant, unrelated)
            ]
        )
        other_team = await seed_team(session, await seed_contest(session), leader)
        await seed_application(session, other_team, unrelated, status="canceled")
        waiting = await seed_account(session)
        reviewing = await seed_account(session)
        await seed_application(session, team, waiting)
        await seed_application(session, team, reviewing, status="reviewing")
        await session.commit()

    async with database.session() as session:
        result = await get_team_space(session, team.team_id, leader.account_id)

    members = {member.account_id: member for member in result.members}
    assert result.viewer_role == "leader"
    assert result.pending_application_count == 2
    assert members[leader.account_id].profile is not None
    applicant_profile = members[applicant.account_id].profile
    assert applicant_profile is not None
    assert applicant_profile.portfolio is not None
    assert members[unrelated.account_id].profile is None
    assert waiting.account_id not in members
    assert reviewing.account_id not in members


async def test_pending_ended_and_unrelated_users_cannot_access_team_space(
    management_database: Database,
) -> None:
    database = management_database
    async with database.session() as session:
        leader = await seed_account(session)
        pending = await seed_account(session)
        ended = await seed_account(session)
        outsider = await seed_account(session)
        team = await seed_team(session, await seed_contest(session), leader)
        await seed_application(session, team, pending, status="reviewing")
        await seed_membership(session, team, ended, ended_at=NOW + timedelta(seconds=1))
        await session.commit()

    for account in (pending, ended, outsider):
        async with database.session() as session:
            with pytest.raises(AppError) as error:
                await get_team_space(session, team.team_id, account.account_id)
            assert error.value.status_code == 403
            assert error.value.code == "FORBIDDEN"
    async with database.session() as session:
        with pytest.raises(AppError) as missing:
            await get_team_space(session, uuid4(), leader.account_id)
        assert missing.value.status_code == 404


async def test_new_request_rechecks_ended_membership_and_changed_profile_visibility(
    management_database: Database,
) -> None:
    database = management_database
    async with database.session() as session:
        leader = await seed_account(session, is_public=True)
        member = await seed_account(session)
        team = await seed_team(session, await seed_contest(session), leader)
        membership = await seed_membership(session, team, member)
        await session.commit()
    async with database.session() as session:
        original = await get_team_space(session, team.team_id, member.account_id)
    assert next(
        m for m in original.members if m.account_id == leader.account_id
    ).profile

    async with database.session() as session:
        await session.execute(
            update(Profile)
            .where(Profile.profile_id == leader.account_id)
            .values(is_public=False)
        )
        await session.commit()
    async with database.session() as session:
        changed = await get_team_space(session, team.team_id, member.account_id)
    assert (
        next(m for m in changed.members if m.account_id == leader.account_id).profile
        is None
    )

    async with database.session() as session:
        await session.execute(
            update(TeamMembership)
            .where(TeamMembership.team_membership_id == membership.team_membership_id)
            .values(
                ended_at=NOW + timedelta(seconds=1), end_reason="application_canceled"
            )
        )
        await session.commit()
    async with database.session() as session:
        with pytest.raises(AppError) as error:
            await get_team_space(session, team.team_id, member.account_id)
    assert error.value.status_code == 403


async def test_workspace_count_and_rows_share_a_snapshot_during_membership_change(
    management_database: Database,
) -> None:
    database = management_database
    async with database.session() as session:
        leader = await seed_account(session)
        viewer = await seed_account(session)
        team = await seed_team(session, await seed_contest(session), leader)
        membership = await seed_membership(session, team, viewer)
        await session.commit()
    changed = False

    async def end_membership() -> None:
        async with database.session() as writer:
            await writer.execute(
                update(TeamMembership)
                .where(
                    TeamMembership.team_membership_id == membership.team_membership_id
                )
                .values(
                    ended_at=NOW + timedelta(seconds=1),
                    end_reason="application_canceled",
                )
            )
            await writer.commit()

    def after_read(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        nonlocal changed
        if (
            not changed
            and "count(" in statement.lower()
            and "team_memberships" in statement
        ):
            changed = True
            await_only(end_membership())

    event.listen(database.engine.sync_engine, "after_cursor_execute", after_read)
    try:
        async with database.session() as session:
            result = await list_workspace_teams(session, viewer.account_id)
    finally:
        event.remove(database.engine.sync_engine, "after_cursor_execute", after_read)

    assert changed
    assert result.pagination.total == 1
    assert len(result.data) == 1
    assert result.data[0].team.member_count == 2
    async with database.session() as session:
        current = await list_workspace_teams(session, viewer.account_id)
    assert current.pagination.total == 0
    assert current.data == []


async def test_reads_do_not_replace_an_existing_callers_transaction(
    management_database: Database,
) -> None:
    async with management_database.session() as session:
        await session.execute(text("SELECT 1"))
        transaction = session.get_transaction()
        with pytest.raises(RuntimeError, match="active transaction"):
            await list_workspace_teams(session, uuid4())
        assert session.get_transaction() is transaction
        assert await session.scalar(select(1)) == 1
