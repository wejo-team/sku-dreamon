"""팀 생성의 재시도·소속 확정·기존 대기 지원 폐기와 롤백을 검증한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.applications import Application, ApplicationEvent
from app.models.notifications import Notification
from app.models.teams import Team, TeamMembership
from app.schemas.team_create import TeamCreate
from app.services.team_create import create_team
from tests.integration.application_review_support import review_data as review_data
from tests.integration.application_support import ApplicationData
from tests.integration.application_support import application_data as application_data

pytestmark = [pytest.mark.integration, pytest.mark.database]


def payload(data: ApplicationData) -> dict[str, object]:
    return {
        "requestId": str(uuid4()),
        "contestId": str(data.contest_id),
        "name": " 새 팀 ",
        "introduction": "함께 공모전에 참여하는 팀입니다.",
        "capacity": "3",
        "roleCodes": ["development"],
        "recruitmentDeadline": {
            "date": (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
        },
    }


async def test_creation_discards_pending_and_retries_without_duplicate(
    review_data: ApplicationData,
) -> None:
    data = review_data
    body = TeamCreate.model_validate(payload(data))
    async with data.database.session() as session:
        result, created = await create_team(session, data.applicant_id, body)
    assert created and result.member_count == 1 and result.name == "새 팀"
    async with data.database.session() as session:
        application = await session.get(Application, data.application_id)
        assert (
            application is not None
            and application.status == "discarded"
            and application.version == 2
        )
        event = await session.scalar(
            select(ApplicationEvent).where(
                ApplicationEvent.reason_code == "team_created_elsewhere"
            )
        )
        assert (
            event is not None
            and event.cause_membership_id is not None
            and event.actor_account_id is None
        )
        assert await session.scalar(select(func.count()).select_from(Notification)) == 1
        repeated, created = await create_team(session, data.applicant_id, body)
        assert not created and repeated.id == result.id
    async with data.database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Notification)) == 1


async def test_request_reuse_and_membership_conflicts(
    review_data: ApplicationData,
) -> None:
    data = review_data
    values = payload(data)
    async with data.database.session() as session:
        await create_team(session, data.applicant_id, TeamCreate.model_validate(values))
    for changes, code in (
        ({"name": "다른 팀"}, "REQUEST_ID_REUSED"),
        ({"requestId": str(uuid4())}, "MEMBERSHIP_CONFLICT"),
    ):
        async with data.database.session() as session:
            with pytest.raises(AppError) as caught:
                await create_team(
                    session,
                    data.applicant_id,
                    TeamCreate.model_validate(values | changes),
                )
            assert caught.value.code == code


async def test_concurrent_same_request_creates_one_team(
    review_data: ApplicationData,
) -> None:
    data = review_data
    body = TeamCreate.model_validate(payload(data) | {"capacity": "1", "roleCodes": []})

    async def create() -> tuple[object, bool]:
        async with data.database.session() as session:
            return await create_team(session, data.applicant_id, body)

    results = await asyncio.gather(create(), create())
    assert sorted(created for _, created in results) == [False, True]
    async with data.database.session() as session:
        team = await session.scalar(
            select(Team).where(Team.leader_account_id == data.applicant_id)
        )
        assert (
            team is not None
            and team.recruitment_state == "closed"
            and team.closed_reason == "capacity_reached"
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TeamMembership)
                .where(TeamMembership.account_id == data.applicant_id)
            )
            == 1
        )
