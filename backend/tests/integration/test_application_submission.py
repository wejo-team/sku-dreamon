"""신규 지원의 권한·재시도·재지원·제출 사건과 알림 원자성을 검증한다."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.models.applications import Application, ApplicationEvent
from app.models.notifications import Notification
from app.models.profiles import Profile
from app.schemas.application_create import ApplicationCreate
from app.services.application_create import submit_application
from tests.integration.application_review_support import review_data as review_data
from tests.integration.application_support import ApplicationData
from tests.integration.application_support import application_data as application_data
from tests.integration.creation_support import creation_client

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def make_public(data: ApplicationData) -> None:
    async with data.database.session() as session:
        await session.execute(
            update(Profile)
            .where(Profile.profile_id == data.applicant_id)
            .values(is_public=True)
        )
        await session.commit()


async def test_submission_http_and_retry_are_atomic(
    review_data: ApplicationData,
) -> None:
    data = review_data
    await make_public(data)
    values = {"requestId": str(uuid4()), "roleCode": "development", "message": "  가  "}
    async with creation_client(data, data.applicant_id) as client:
        path = f"/api/v1/teams/{data.other_team_id}/applications"
        first = await client.post(path, json=values)
        assert first.status_code == 201, first.text
        assert (
            first.json()["data"]["message"] == "가"
            and first.json()["data"]["status"] == "submitted"
        )
        second = await client.post(path, json=values | {"message": "가"})
        assert second.status_code == 200 and second.json() == first.json()
        assert (
            await client.post(path, json=values | {"message": "다름"})
        ).status_code == 409
    async with data.database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Notification)) == 2
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Application)
                .where(Application.team_id == data.other_team_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ApplicationEvent)
                .where(ApplicationEvent.team_id == data.other_team_id)
            )
            == 1
        )


async def test_private_profile_blocks_new_submission(
    review_data: ApplicationData,
) -> None:
    from app.core.exceptions import AppError

    async with review_data.database.session() as session:
        with pytest.raises(AppError) as caught:
            await submit_application(
                session,
                review_data.applicant_id,
                review_data.other_team_id,
                ApplicationCreate(requestId=uuid4(), roleCode="development"),
            )
        assert caught.value.code == "PROFILE_PRIVATE"


async def test_canceled_attempt_can_reapply_but_rejected_cannot(
    review_data: ApplicationData,
) -> None:
    from app.core.exceptions import AppError
    from app.services.application_review import change_review_status
    from app.services.applications import cancel_application

    data = review_data
    await make_public(data)
    async with data.database.session() as session:
        await cancel_application(session, data.application_id, data.applicant_id, 1)
    async with data.database.session() as session:
        response, created = await submit_application(
            session,
            data.applicant_id,
            data.team_id,
            ApplicationCreate(requestId=uuid4(), roleCode="planning"),
        )
        assert created and response.id != data.application_id
    async with data.database.session() as session:
        await change_review_status(session, response.id, data.leader_id, 1, "rejected")
    async with data.database.session() as session:
        with pytest.raises(AppError) as caught:
            await submit_application(
                session,
                data.applicant_id,
                data.team_id,
                ApplicationCreate(requestId=uuid4(), roleCode="planning"),
            )
        assert caught.value.code == "REAPPLICATION_NOT_ALLOWED"
