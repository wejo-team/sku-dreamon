"""하위 알림 생성이 호출자의 사건·업무 트랜잭션을 먼저 커밋하지 않는지 검증한다."""

from datetime import timedelta
from uuid import uuid4

import pytest

from app.models.applications import Application, ApplicationEvent
from app.models.notifications import Notification
from app.services.notifications import create_notification
from tests.integration.test_notifications import NOW, NotificationData
from tests.integration.test_notifications import notification_data as notification_data

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_created_notification_and_event_rollback_with_the_callers_transaction(
    notification_data: NotificationData,
) -> None:
    database = notification_data.database
    async with database.session() as session:
        prior_notice = await session.get(Notification, notification_data.owned_ids[1])
        assert prior_notice is not None
        prior_event = await session.get(ApplicationEvent, prior_notice.event_id)
        assert prior_event is not None
        application_id = prior_event.application_id
        application = await session.get(Application, application_id)
        assert application is not None and application.status == "reviewing"
        application.status = "rejected"
        application.version += 1
        application.status_changed_at = NOW + timedelta(seconds=3)
        event_id = uuid4()
        session.add(
            ApplicationEvent(
                application_event_id=event_id,
                application_id=application_id,
                team_id=application.team_id,
                contest_id=application.contest_id,
                applicant_account_id=application.applicant_account_id,
                application_version=application.version,
                from_status="reviewing",
                to_status="rejected",
                actor_account_id=notification_data.other_account_id,
                reason_code="rejected",
                occurred_at=application.status_changed_at,
            )
        )
        await session.flush()
        notification = await create_notification(
            session,
            event_id=event_id,
            recipient_id=notification_data.account_id,
            kind="application_status_changed",
        )
        notification_id = notification.notification_id
        async with database.session() as observer:
            assert await observer.get(Notification, notification_id) is None
            assert await observer.get(ApplicationEvent, event_id) is None
        await session.rollback()
    async with database.session() as observer:
        assert await observer.get(Notification, notification_id) is None
        assert await observer.get(ApplicationEvent, event_id) is None
        application = await observer.get(Application, application_id)
        assert application is not None
        assert application.status == "reviewing" and application.version == 2
