"""본인 지원의 이력·필터·보정 페이지와 현재 소속을 HTTP로 확인한다."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.domains.applications.models import Application, ApplicationEvent
from tests.integration.application_support import (
    ApplicationData,
    application_client,
    make_application,
)
from tests.integration.application_support import application_data as application_data
from tests.integration.test_application_cancellation import set_status

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_own_history_stable_order_filter_and_clamped_page(
    application_data: ApplicationData,
) -> None:
    data = application_data
    now = datetime.now(UTC)
    async with data.database.session() as session:
        for _ in range(4):
            historical = make_application(
                data.team_id, data.contest_id, data.applicant_id, now
            )
            historical.status = "canceled"
            historical.version = 2
            session.add(historical)
            await session.flush()
            session.add(
                ApplicationEvent(
                    application_id=historical.application_id,
                    team_id=data.team_id,
                    contest_id=data.contest_id,
                    applicant_account_id=data.applicant_id,
                    application_version=2,
                    from_status="submitted",
                    to_status="canceled",
                    actor_account_id=data.applicant_id,
                    reason_code="canceled",
                    occurred_at=now,
                )
            )
        stranger = make_application(
            data.team_id, data.contest_id, data.stranger_id, now
        )
        session.add(stranger)
        await session.commit()
        expected = list(
            await session.scalars(
                select(Application.application_id)
                .where(Application.applicant_account_id == data.applicant_id)
                .order_by(
                    Application.submitted_at.desc(), Application.application_id.desc()
                )
            )
        )
    async with application_client(data, data.applicant_id) as client:
        first = await client.get("/api/v1/me/applications", params={"pageSize": 2})
        assert first.status_code == 200
        body = first.json()
        assert body["pagination"] == {
            "page": 1,
            "pageSize": 2,
            "total": 5,
            "totalPages": 3,
        }
        assert [item["application"]["id"] for item in body["data"]] == [
            str(value) for value in expected[:2]
        ]
        team = body["data"][0]["team"]
        assert team["memberCount"] == 1 and team["isRecruiting"] is True
        assert team["fieldCodes"] == ["it_technology"] and team["roleCodes"] == [
            "development"
        ]
        assert all(not item["isCurrentMember"] for item in body["data"])
        last = await client.get(
            "/api/v1/me/applications", params={"pageSize": 2, "page": 999}
        )
        assert last.status_code == 200
        assert last.json()["pagination"] == {
            "page": 3,
            "pageSize": 2,
            "total": 5,
            "totalPages": 3,
        }
        assert last.json()["data"][0]["application"]["id"] == str(expected[-1])
        filtered = await client.get(
            "/api/v1/me/applications", params={"status": "submitted"}
        )
        assert filtered.status_code == 200
        assert filtered.json()["pagination"]["total"] == 1
        assert filtered.json()["data"][0]["application"]["id"] == str(
            data.application_id
        )


async def test_selected_then_canceled_updates_current_membership(
    application_data: ApplicationData,
) -> None:
    data = application_data
    await set_status(data, "selected")
    async with application_client(data, data.applicant_id) as client:
        before = await client.get("/api/v1/me/applications")
        assert before.status_code == 200
        assert before.json()["data"][0]["isCurrentMember"] is True
        assert before.json()["data"][0]["team"]["memberCount"] == 2
        canceled = await client.put(
            f"/api/v1/applications/{data.application_id}/cancellation",
            json={"expectedVersion": "2"},
        )
        assert canceled.status_code == 200
        after = await client.get("/api/v1/me/applications")
        assert after.status_code == 200
        item = after.json()["data"][0]
        assert (
            item["application"]["status"] == "canceled"
            and item["isCurrentMember"] is False
        )
        assert (
            item["team"]["memberCount"] == 1
            and item["team"]["recruitmentState"] == "closed"
        )


async def test_empty_auth_and_query_validation(
    application_data: ApplicationData,
) -> None:
    data = application_data
    async with application_client(data, data.leader_id) as client:
        response = await client.get("/api/v1/me/applications", params={"page": 99})
        assert response.status_code == 200
        assert response.json() == {
            "data": [],
            "pagination": {"page": 1, "pageSize": 20, "total": 0, "totalPages": 0},
        }
        for params in (
            {"status": "made_up"},
            {"page": 0},
            {"pageSize": 101},
            {"page_size": 20},
        ):
            assert (
                await client.get("/api/v1/me/applications", params=params)
            ).status_code == 422
    async with application_client(data, None) as client:
        assert (await client.get("/api/v1/me/applications")).status_code == 401
