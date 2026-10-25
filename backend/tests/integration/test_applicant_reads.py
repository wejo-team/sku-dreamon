"""지원받은 팀장의 최신 프로필 조회와 일반 열람 권한의 경계를 검증한다."""

from uuid import uuid4

import pytest
from sqlalchemy import Select, update

from app.models.applications import Application
from app.models.profiles import Profile
from app.schemas.application_review import ApplicantSearch
from app.services import application_review as review_service
from tests.integration.application_review_support import review_client
from tests.integration.application_review_support import review_data as review_data
from tests.integration.application_support import ApplicationData
from tests.integration.application_support import application_data as application_data

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_receiving_leader_reads_current_private_profile_and_candidates(
    review_data: ApplicationData,
) -> None:
    data = review_data
    async with review_client(data, data.leader_id) as client:
        detail = await client.get(
            f"/api/v1/applications/{data.application_id}/applicant"
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["profile"]["isPublic"] is False
        assert detail.json()["data"]["isSelectionCandidate"] is True
        async with data.database.session() as session:
            await session.execute(
                update(Profile)
                .where(Profile.profile_id == data.applicant_id)
                .values(real_name="수정 이름", version=2)
            )
            await session.execute(
                update(Application)
                .where(Application.application_id == data.application_id)
                .values(status="canceled", version=2)
            )
            await session.commit()
        history = await client.get(
            f"/api/v1/applications/{data.application_id}/applicant"
        )
        body = history.json()["data"]
        assert body["profile"]["realName"] == "수정 이름"
        assert body["profile"]["version"] == "2"
        assert body["isSelectionCandidate"] is False
        page = await client.get(f"/api/v1/teams/{data.team_id}/applicants?page=999")
        assert page.status_code == 200
        assert page.json()["pagination"] == {
            "page": 1,
            "pageSize": 20,
            "total": 1,
            "totalPages": 1,
        }
        assert page.json()["data"][0] == body
        empty = await client.get(
            f"/api/v1/teams/{data.team_id}/applicants?status=submitted"
        )
        assert empty.json()["data"] == []
        assert empty.json()["pagination"]["totalPages"] == 0


async def test_applicant_visibility_distinguishes_action_denial_from_hidden_resource(
    review_data: ApplicationData,
) -> None:
    data = review_data
    for account_id, status in (
        (data.applicant_id, 403),
        (data.stranger_id, 404),
        (None, 401),
    ):
        async with review_client(data, account_id) as client:
            response = await client.get(
                f"/api/v1/applications/{data.application_id}/applicant"
            )
            assert response.status_code == status
    async with review_client(data, data.stranger_id) as client:
        assert (
            await client.get(f"/api/v1/teams/{data.team_id}/applicants")
        ).status_code == 403
        assert (
            await client.get(f"/api/v1/teams/{uuid4()}/applicants")
        ).status_code == 404
    async with review_client(data, data.leader_id) as client:
        for query in ("status=unknown", "page=0", "pageSize=101", "page_size=1"):
            assert (
                await client.get(f"/api/v1/teams/{data.team_id}/applicants?{query}")
            ).status_code == 422


async def test_applicant_count_profile_and_status_share_one_snapshot(
    review_data: ApplicationData, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = review_data
    async with data.database.session() as reader:
        original_scalar = reader.scalar

        async def count_then_change(statement: Select[tuple[int]]) -> int | None:
            count = await original_scalar(statement)
            async with data.database.session() as writer:
                await writer.execute(
                    update(Application)
                    .where(Application.application_id == data.application_id)
                    .values(status="canceled", version=2)
                )
                await writer.execute(
                    update(Profile)
                    .where(Profile.profile_id == data.applicant_id)
                    .values(real_name="다음 요청의 이름", version=2)
                )
                await writer.commit()
            return count

        monkeypatch.setattr(reader, "scalar", count_then_change)
        page = await review_service.list_applicants(
            reader,
            data.team_id,
            data.leader_id,
            ApplicantSearch.model_validate({"status": "submitted"}),
        )
        assert page.pagination.total == len(page.data) == 1
        assert page.data[0].profile.real_name == "검토 사용자"
        assert page.data[0].application.status == "submitted"
    async with data.database.session() as fresh:
        page = await review_service.list_applicants(
            fresh,
            data.team_id,
            data.leader_id,
            ApplicantSearch.model_validate({"status": "submitted"}),
        )
        assert page.pagination.total == 0
