"""모집 변경 HTTP의 실제 인증·CSRF·버전·업무 실패 경계를 검증한다."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.core.db.session import Database
from app.dependencies.csrf import CSRF_HEADER_NAME
from app.models.teams import Team
from app.services import teams as management
from tests.integration.team_management_http_support import management_client
from tests.integration.team_management_support import NOW, prepare_team, seed_account
from tests.integration.team_management_support import (
    management_database as management_database,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(management, "_utcnow", lambda: NOW)


async def test_authentication_precedes_csrf_and_versions_are_strict(
    management_database: Database,
) -> None:
    database = management_database
    team_id, owner_id = await prepare_team(database)
    paths = [
        f"/api/v1/teams/{team_id}/recruitment/{action}"
        for action in ("closure", "reopening")
    ]
    async with management_client(database, None) as anonymous:
        for path in paths:
            response = await anonymous.put(path, json={"expectedVersion": "1"})
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    async with management_client(database, owner_id) as client:
        for invalid in (
            {"expectedVersion": 1},
            {"expected_version": "1"},
            {"expectedVersion": "0"},
            {"expectedVersion": "01"},
        ):
            assert (await client.put(paths[0], json=invalid)).status_code == 422
        del client.headers[CSRF_HEADER_NAME]
        for path in paths:
            assert (
                await client.put(path, json={"expectedVersion": "1"})
            ).status_code == 403
    async with database.session() as session:
        team = await session.get(Team, team_id)
        assert team is not None and team.version == 1


async def test_http_commands_return_current_state_and_noop_is_stable(
    management_database: Database,
) -> None:
    database = management_database
    team_id, owner_id = await prepare_team(database)
    path = f"/api/v1/teams/{team_id}/recruitment"
    async with management_client(database, owner_id) as client:
        closed = await client.put(f"{path}/closure", json={"expectedVersion": "1"})
        assert closed.status_code == 200
        assert closed.json()["data"]["team"]["version"] == "2"
        noop = await client.put(f"{path}/closure", json={"expectedVersion": "2"})
        assert noop.status_code == 200 and noop.json() == closed.json()
        stale = await client.put(f"{path}/closure", json={"expectedVersion": "1"})
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
        opened = await client.put(f"{path}/reopening", json={"expectedVersion": "2"})
        assert opened.status_code == 200
        team = opened.json()["data"]["team"]
        assert (
            team["version"],
            team["recruitmentState"],
            team["closedReason"],
            team["isRecruiting"],
        ) == ("3", "open", None, True)


async def test_http_permission_missing_team_and_deadline(
    management_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = management_database
    team_id, owner_id = await prepare_team(database)
    async with database.session() as session:
        outsider = await seed_account(session)
        await session.commit()
        outsider_id = outsider.account_id
    async with management_client(database, outsider_id) as client:
        response = await client.put(
            f"/api/v1/teams/{team_id}/recruitment/closure",
            json={"expectedVersion": "1"},
        )
        assert response.status_code == 403
    async with management_client(database, owner_id) as client:
        missing = await client.put(
            f"/api/v1/teams/{uuid4()}/recruitment/closure",
            json={"expectedVersion": "1"},
        )
        assert missing.status_code == 404
        monkeypatch.setattr(management, "_utcnow", lambda: NOW + timedelta(days=7))
        expired = await client.put(
            f"/api/v1/teams/{team_id}/recruitment/reopening",
            json={"expectedVersion": "1"},
        )
        assert expired.status_code == 409
        assert expired.json()["error"]["code"] == "RECRUITMENT_DEADLINE_PASSED"


async def test_two_http_requests_use_one_expected_version(
    management_database: Database,
) -> None:
    database = management_database
    team_id, owner_id = await prepare_team(database)
    async with (
        management_client(database, owner_id) as first,
        management_client(database, owner_id) as second,
    ):
        path = f"/api/v1/teams/{team_id}/recruitment/closure"
        responses = await asyncio.gather(
            first.put(path, json={"expectedVersion": "1"}),
            second.put(path, json={"expectedVersion": "1"}),
        )
    assert sorted(response.status_code for response in responses) == [200, 409]


async def test_database_failure_rolls_back_recruitment_change(
    management_database: Database,
) -> None:
    database = management_database
    team_id, owner_id = await prepare_team(database)

    def fail_update(*args: object) -> None:
        raise RuntimeError("테스트용 저장 실패")

    event.listen(Team, "before_update", fail_update)
    try:
        async with management_client(database, owner_id) as client:
            response = await client.put(
                f"/api/v1/teams/{team_id}/recruitment/closure",
                json={"expectedVersion": "1"},
            )
            assert response.status_code == 500
    finally:
        event.remove(Team, "before_update", fail_update)
    async with database.session() as session:
        team = await session.get(Team, team_id)
        assert team is not None
        assert (team.version, team.recruitment_state, team.closed_reason) == (
            1,
            "open",
            None,
        )
