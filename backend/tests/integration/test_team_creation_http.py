"""팀 생성의 HTTP 인증·재시도, 실패 롤백과 선발 경합을 검증한다."""

import asyncio
from typing import Literal
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.applications import Application
from app.models.notifications import Notification
from app.models.teams import Team, TeamMembership
from app.schemas.team_create import TeamCreate
from app.services import team_create
from app.services.application_review import select_application
from tests.integration.application_support import ApplicationData
from tests.integration.creation_support import creation_client
from tests.integration.test_team_creation import payload

pytest_plugins = [
    "tests.integration.application_support",
    "tests.integration.application_review_support",
]
pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_http_auth_csrf_alias_and_retry_contract(
    review_data: ApplicationData,
) -> None:
    values = payload(review_data)
    async with creation_client(review_data, None) as client:
        assert (await client.post("/api/v1/teams", json=values)).status_code == 401
    async with creation_client(review_data, review_data.applicant_id) as client:
        assert (
            await client.post(
                "/api/v1/teams", json=values, headers={"X-CSRF-Token": "bad"}
            )
        ).status_code == 403
        assert (
            await client.post(
                "/api/v1/teams",
                json=values | {"leaderAccountId": str(review_data.leader_id)},
            )
        ).status_code == 422
        first = await client.post("/api/v1/teams", json=values)
        assert first.status_code == 201, first.text
        second = await client.post("/api/v1/teams", json=values)
        assert second.status_code == 200 and first.json() == second.json()
        operation = (await client.get("/openapi.json")).json()["paths"][
            "/api/v1/teams"
        ]["post"]
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]
            == operation["responses"]["201"]["content"]["application/json"]["schema"]
        )


async def test_notification_failure_rolls_back_every_change(
    review_data: ApplicationData, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(
        session: AsyncSession,
        *,
        event_id: UUID,
        recipient_id: UUID,
        kind: Literal["application_status_changed", "new_application"],
    ) -> Notification:
        raise RuntimeError("notification failure")

    monkeypatch.setattr(team_create, "create_notification", fail)
    async with review_data.database.session() as session:
        with pytest.raises(RuntimeError):
            await team_create.create_team(
                session,
                review_data.applicant_id,
                TeamCreate.model_validate(payload(review_data)),
            )
    async with review_data.database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Team)
                .where(Team.leader_account_id == review_data.applicant_id)
            )
            == 0
        )
        application = await session.get(Application, review_data.application_id)
        assert (
            application is not None
            and application.status == "submitted"
            and application.version == 1
        )
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0


@pytest.mark.parametrize(
    "change,code",
    [
        ({"capacity": "6"}, "CAPACITY_OUT_OF_RANGE"),
        ({"roleCodes": ["invalid"]}, "INVALID_CATALOG_SELECTION"),
    ],
)
async def test_official_capacity_and_roles(
    review_data: ApplicationData, change: dict[str, object], code: str
) -> None:
    async with review_data.database.session() as session:
        with pytest.raises(AppError) as caught:
            await team_create.create_team(
                session,
                review_data.applicant_id,
                TeamCreate.model_validate(payload(review_data) | change),
            )
        assert caught.value.code == code


async def test_creation_races_selection_without_double_membership(
    review_data: ApplicationData,
) -> None:
    async def create() -> str:
        async with review_data.database.session() as session:
            try:
                await team_create.create_team(
                    session,
                    review_data.applicant_id,
                    TeamCreate.model_validate(payload(review_data)),
                )
                return "created"
            except AppError:
                return "conflict"

    async def select_member() -> str:
        async with review_data.database.session() as session:
            try:
                await select_application(
                    session, review_data.application_id, review_data.leader_id, 1
                )
                return "selected"
            except AppError:
                return "conflict"

    results = await asyncio.gather(create(), select_member())
    assert results.count("conflict") == 1
    async with review_data.database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TeamMembership)
                .where(
                    TeamMembership.account_id == review_data.applicant_id,
                    TeamMembership.ended_at.is_(None),
                )
            )
            == 1
        )
