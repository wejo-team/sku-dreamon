"""팀 공간 HTTP의 인증·현재 소속·비공개 프로필 경계를 검증한다."""

from uuid import uuid4

import pytest

from app.core.db.session import Database
from app.domains.auth.models import Account
from app.domains.teams.models import Team
from tests.integration.team_management_http_support import management_client
from tests.integration.team_management_support import (
    management_database as management_database,
)
from tests.integration.team_management_support import (
    prepare_team,
    seed_account,
    seed_application,
    seed_contest,
    seed_membership,
    seed_team,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_workspace_http_requires_login_and_current_membership(
    management_database: Database,
) -> None:
    database = management_database
    team_id, owner_id = await prepare_team(database)
    path = f"/api/v1/teams/{team_id}/space"
    async with management_client(database, None) as client:
        assert (await client.get("/api/v1/me/teams")).status_code == 401
        assert (await client.get(path)).status_code == 401
    async with database.session() as session:
        outsider = await seed_account(session)
        team = await session.get(Team, team_id)
        assert team is not None
        await seed_application(session, team, outsider)
        await session.commit()
        outsider_id = outsider.account_id
    async with management_client(database, outsider_id) as client:
        assert (await client.get(path)).status_code == 403
        assert (await client.get(f"/api/v1/teams/{uuid4()}/space")).status_code == 404
        empty = await client.get("/api/v1/me/teams?page=5&pageSize=2")
        assert empty.status_code == 200
        assert empty.json()["data"] == []
        assert empty.json()["pagination"] == {
            "page": 1,
            "pageSize": 2,
            "total": 0,
            "totalPages": 0,
        }
    async with management_client(database, owner_id) as client:
        listing = await client.get("/api/v1/me/teams?page=100&pageSize=1")
        assert listing.status_code == 200
        assert listing.headers["Cache-Control"] == "no-store"
        assert listing.json()["pagination"]["page"] == 1
        item = listing.json()["data"][0]
        assert item["membershipRole"] == "leader"
        assert item["pendingApplicationCount"] == 1
        for query in ("page=0", "pageSize=101", "unknown=1", "page_size=2"):
            assert (await client.get(f"/api/v1/me/teams?{query}")).status_code == 422


async def test_team_members_see_identity_but_not_private_profiles_or_pending_count(
    management_database: Database,
) -> None:
    database = management_database
    team_id, owner_id = await prepare_team(database)
    async with database.session() as session:
        team = await session.get(Team, team_id)
        assert team is not None
        member = await seed_account(session, real_name="현재 팀원")
        other_member = await seed_account(session, real_name="비공개 팀원")
        await seed_membership(session, team, member)
        await seed_membership(session, team, other_member)
        await session.commit()
        member_id, other_id = member.account_id, other_member.account_id
    path = f"/api/v1/teams/{team_id}/space"
    async with management_client(database, member_id) as client:
        response = await client.get(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        data = response.json()["data"]
        assert data["viewerRole"] == "member"
        assert data["pendingApplicationCount"] is None
        members = {item["accountId"]: item for item in data["members"]}
        assert members[str(member_id)]["profile"] is not None
        assert members[str(other_id)]["realName"] == "비공개 팀원"
        assert members[str(other_id)]["profile"] is None
        assert members[str(owner_id)]["profile"] is None
        assert "private-portfolio" not in str(members[str(other_id)])
    async with management_client(database, owner_id) as client:
        response = await client.get(path)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["viewerRole"] == "leader"
        assert data["pendingApplicationCount"] == 0
        assert all(member["profile"] is not None for member in data["members"])


async def test_space_does_not_silently_omit_a_member_without_a_profile(
    management_database: Database,
) -> None:
    database = management_database
    async with database.session() as session:
        owner = Account(
            account_id=uuid4(),
            login_id_normalized="noprofileowner",
            password_hash="test-only",
        )
        session.add(owner)
        await session.flush()
        contest = await seed_contest(session)
        team = await seed_team(session, contest, owner)
        member = await seed_account(session)
        await seed_membership(session, team, member)
        await session.commit()
        team_id, member_id = team.team_id, member.account_id
    async with management_client(database, member_id) as client:
        response = await client.get(f"/api/v1/teams/{team_id}/space")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "data" not in response.json()
