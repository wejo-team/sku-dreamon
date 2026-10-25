"""선발의 소속·폐기·정원·마감 경쟁과 전체 롤백을 실제 PostgreSQL에서 검증한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, text, update

from app.core.exceptions import AppError
from app.dependencies.csrf import CSRF_HEADER_NAME
from app.models.applications import Application, ApplicationEvent
from app.models.auth import Account
from app.models.contests import Contest
from app.models.notifications import Notification
from app.models.teams import Team, TeamMembership
from app.services import application_review as review_service
from app.services.applications import cancel_application
from tests.integration.application_review_support import review_client
from tests.integration.application_review_support import review_data as review_data
from tests.integration.application_support import (
    ApplicationData,
    make_application,
    make_team,
)
from tests.integration.application_support import application_data as application_data
from tests.integration.test_team_integrity import contest

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def add_attempt(
    data: ApplicationData,
    team_id: UUID,
    account_id: UUID,
    contest_id: UUID | None = None,
) -> UUID:
    async with data.database.session() as session:
        attempt = make_application(
            team_id,
            contest_id or data.contest_id,
            account_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )
        session.add(attempt)
        await session.flush()
        session.add(
            ApplicationEvent(
                application_id=attempt.application_id,
                team_id=team_id,
                contest_id=attempt.contest_id,
                applicant_account_id=account_id,
                application_version=1,
                from_status=None,
                to_status="submitted",
                actor_account_id=account_id,
                reason_code="submitted",
                occurred_at=attempt.submitted_at,
            )
        )
        await session.commit()
        return attempt.application_id


async def test_selection_closes_full_team_discards_only_same_contest_pending_and_noop(
    review_data: ApplicationData,
) -> None:
    data = review_data
    other_id = await add_attempt(data, data.other_team_id, data.applicant_id)
    async with data.database.session() as session:
        another_contest = contest()
        session.add(another_contest)
        await session.flush()
        another_team = make_team(
            another_contest.contest_id, data.stranger_id, datetime.now(UTC)
        )
        session.add(another_team)
        await session.flush()
        another_team_id, another_contest_id = (
            another_team.team_id,
            another_contest.contest_id,
        )
        await session.execute(
            update(Team)
            .where(Team.team_id == data.team_id)
            .values(
                target_capacity=2,
                recruitment_state="closed",
                closed_reason="leader_closed",
                recruitment_closes_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await session.commit()
    unrelated_id = await add_attempt(
        data, another_team_id, data.applicant_id, another_contest_id
    )
    path = f"/api/v1/applications/{data.application_id}/selection"
    async with review_client(data, data.leader_id) as client:
        response = await client.put(path, json={"expectedVersion": "1"})
        assert response.status_code == 200
        body = response.json()["data"]
        assert set(body) == {"application", "team", "membershipId"}
        assert body["application"]["status"] == "selected"
        assert body["team"]["memberCount"] == 2
        assert body["team"]["recruitmentState"] == "closed"
        assert body["team"]["closedReason"] == "capacity_reached"
        assert body["team"]["version"] == "2"
        async with data.database.session() as session:
            await session.execute(
                update(Contest)
                .where(Contest.contest_id == data.contest_id)
                .values(registration_closes_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
        stale = await client.put(path, json={"expectedVersion": "1"})
        assert (
            stale.status_code == 409
            and stale.json()["error"]["code"] == "VERSION_CONFLICT"
        )
        repeated = await client.put(path, json={"expectedVersion": "2"})
        assert repeated.status_code == 200
        assert repeated.json()["data"]["membershipId"] == body["membershipId"]
    async with data.database.session() as session:
        other = await session.get(Application, other_id)
        untouched = await session.get(Application, unrelated_id)
        assert other is not None and other.status == "discarded" and other.version == 2
        assert (
            untouched is not None
            and untouched.status == "submitted"
            and untouched.version == 1
        )
        discarded_event = await session.scalar(
            select(ApplicationEvent).where(
                ApplicationEvent.application_id == other_id,
                ApplicationEvent.application_version == 2,
            )
        )
        assert (
            discarded_event is not None
            and discarded_event.reason_code == "selected_elsewhere"
        )
        source = await session.get(ApplicationEvent, discarded_event.cause_event_id)
        assert (
            source is not None
            and source.application_id == data.application_id
            and source.to_status == "selected"
        )
        notices = (await session.scalars(select(Notification))).all()
        assert len(notices) == 2 and all(
            n.recipient_account_id == data.applicant_id for n in notices
        )
        membership = await session.get(TeamMembership, UUID(body["membershipId"]))
        assert (
            membership is not None
            and membership.source_application_id == data.application_id
        )
        assert membership.ended_at is None


async def test_selection_notification_failure_rolls_back_every_change(
    review_data: ApplicationData,
) -> None:
    data = review_data
    other_id = await add_attempt(data, data.other_team_id, data.applicant_id)

    def fail_notice(*args: object) -> None:
        raise RuntimeError("notification unavailable")

    event.listen(Notification, "before_insert", fail_notice)
    try:
        async with review_client(data, data.leader_id) as client:
            response = await client.put(
                f"/api/v1/applications/{data.application_id}/selection",
                json={"expectedVersion": "1"},
            )
            assert response.status_code == 500
    finally:
        event.remove(Notification, "before_insert", fail_notice)
    async with data.database.session() as session:
        for identifier in (data.application_id, other_id):
            attempt = await session.get(Application, identifier)
            assert (
                attempt is not None
                and attempt.status == "submitted"
                and attempt.version == 1
            )
        team = await session.get(Team, data.team_id)
        assert team is not None and team.version == 1
        assert (
            await session.scalar(select(func.count()).select_from(TeamMembership)) == 2
        )
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationEvent))
            == 2
        )
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0


async def test_two_candidates_competing_for_last_seat_have_one_winner(
    review_data: ApplicationData,
) -> None:
    data = review_data
    async with data.database.session() as session:
        second_account = Account(
            account_id=uuid4(),
            login_id_normalized="secondcandidate",
            password_hash="test-only",
        )
        session.add(second_account)
        await session.execute(
            update(Team).where(Team.team_id == data.team_id).values(target_capacity=2)
        )
        await session.commit()
        second_account_id = second_account.account_id
    second_id = await add_attempt(data, data.team_id, second_account_id)
    async with (
        review_client(data, data.leader_id) as first,
        review_client(data, data.leader_id) as second,
    ):
        responses = await asyncio.gather(
            first.put(
                f"/api/v1/applications/{data.application_id}/selection",
                json={"expectedVersion": "1"},
            ),
            second.put(
                f"/api/v1/applications/{second_id}/selection",
                json={"expectedVersion": "1"},
            ),
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    failure = next(r for r in responses if r.status_code == 409)
    assert failure.json()["error"]["code"] == "TEAM_FULL"
    async with data.database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TeamMembership)
                .where(
                    TeamMembership.team_id == data.team_id,
                    TeamMembership.ended_at.is_(None),
                )
            )
            == 2
        )
        assert await session.scalar(select(func.count()).select_from(Notification)) == 1


async def test_two_teams_selecting_one_applicant_keep_one_contest_membership(
    review_data: ApplicationData,
) -> None:
    data = review_data
    other_id = await add_attempt(data, data.other_team_id, data.applicant_id)
    async with (
        review_client(data, data.leader_id) as first,
        review_client(data, data.stranger_id) as second,
    ):
        responses = await asyncio.gather(
            first.put(
                f"/api/v1/applications/{data.application_id}/selection",
                json={"expectedVersion": "1"},
            ),
            second.put(
                f"/api/v1/applications/{other_id}/selection",
                json={"expectedVersion": "1"},
            ),
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["error"]["code"]
        == "VERSION_CONFLICT"
    )
    async with data.database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TeamMembership)
                .where(
                    TeamMembership.account_id == data.applicant_id,
                    TeamMembership.ended_at.is_(None),
                )
            )
            == 1
        )
        states = (
            await session.scalars(
                select(Application.status).where(
                    Application.application_id.in_([data.application_id, other_id])
                )
            )
        ).all()
        assert sorted(states) == ["discarded", "selected"]


async def test_selection_checks_deadline_after_waiting_for_team_lock(
    review_data: ApplicationData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = review_data
    now = datetime.now(UTC)
    deadline = now + timedelta(minutes=1)
    current = [now]
    monkeypatch.setattr(review_service, "_utcnow", lambda: current[0])
    async with data.database.session() as session:
        await session.execute(
            update(Contest)
            .where(Contest.contest_id == data.contest_id)
            .values(registration_closes_at=deadline)
        )
        await session.commit()
    async with data.database.session() as holder:
        await holder.scalar(
            select(Team).where(Team.team_id == data.team_id).with_for_update()
        )

        async def select_waiter() -> None:
            async with data.database.session() as session:
                await review_service.select_application(
                    session, data.application_id, data.leader_id, 1
                )

        pending = asyncio.create_task(select_waiter())
        try:
            async with asyncio.timeout(5), data.database.engine.connect() as observer:
                application_name = await observer.scalar(text("SHOW application_name"))
                # 실제 DB 잠금 대기가 시작된 뒤 시각을 경계로 옮긴다.
                while True:
                    waiting = await observer.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                            "WHERE application_name = :name "
                            "AND wait_event_type = 'Lock')"
                        ),
                        {"name": application_name},
                    )
                    await observer.commit()
                    if waiting:
                        break
                    await asyncio.sleep(0.01)
            current[0] = deadline
            await holder.commit()
            with pytest.raises(AppError) as failure:
                await pending
            assert failure.value.code == "CONTEST_NOT_OPEN"
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


async def test_selection_requires_receiving_leader_current_version_and_csrf(
    review_data: ApplicationData,
) -> None:
    data = review_data
    path = f"/api/v1/applications/{data.application_id}/selection"
    for viewer, status in (
        (None, 401),
        (data.applicant_id, 403),
        (data.stranger_id, 404),
    ):
        async with review_client(data, viewer) as client:
            assert (
                await client.put(path, json={"expectedVersion": "1"})
            ).status_code == status
    async with review_client(data, data.leader_id) as client:
        del client.headers[CSRF_HEADER_NAME]
        assert (
            await client.put(path, json={"expectedVersion": "1"})
        ).status_code == 403
    async with data.database.session() as session:
        await cancel_application(session, data.application_id, data.applicant_id, 1)
    async with review_client(data, data.leader_id) as client:
        for version, code in (
            ("1", "VERSION_CONFLICT"),
            ("2", "INVALID_APPLICATION_STATE"),
        ):
            result = await client.put(path, json={"expectedVersion": version})
            assert result.status_code == 409 and result.json()["error"]["code"] == code


async def test_cancel_and_selection_race_preserves_status_and_membership(
    review_data: ApplicationData,
) -> None:
    data = review_data

    async def select_once() -> str:
        async with data.database.session() as session:
            try:
                await review_service.select_application(
                    session, data.application_id, data.leader_id, 1
                )
                return "selected"
            except AppError as error:
                return error.code

    async def cancel_once() -> str:
        async with data.database.session() as session:
            try:
                await cancel_application(
                    session, data.application_id, data.applicant_id, 1
                )
                return "canceled"
            except AppError as error:
                return error.code

    outcomes = await asyncio.gather(select_once(), cancel_once())
    assert outcomes.count("VERSION_CONFLICT") == 1
    async with data.database.session() as session:
        application = await session.get(Application, data.application_id)
        assert application is not None and application.version == 2
        membership = await session.scalar(
            select(TeamMembership).where(
                TeamMembership.source_application_id == data.application_id
            )
        )
        if application.status == "selected":
            assert membership is not None and membership.ended_at is None
            await cancel_application(session, data.application_id, data.applicant_id, 2)
    async with data.database.session() as session:
        application = await session.get(Application, data.application_id)
        assert application is not None and application.status == "canceled"
        active = await session.scalar(
            select(TeamMembership).where(
                TeamMembership.source_application_id == data.application_id,
                TeamMembership.ended_at.is_(None),
            )
        )
        assert active is None
