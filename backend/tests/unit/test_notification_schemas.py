"""읽음 ID 집합의 중복·빈 입력·외부 필드 거부를 검증한다."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domains.notifications.schemas import ReadNotifications


def test_read_notifications_accepts_a_nonempty_unique_uuid_list() -> None:
    first, second = uuid4(), uuid4()
    payload = ReadNotifications.model_validate(
        {"notificationIds": [str(first), str(second)]}
    )
    assert payload.notification_ids == [first, second]


@pytest.mark.parametrize(
    "payload",
    [
        {"notificationIds": []},
        {"notificationIds": None},
        {"notificationIds": ["not-a-uuid"]},
        {"notification_ids": [str(uuid4())]},
        {"notificationIds": [str(uuid4())], "accountId": str(uuid4())},
    ],
)
def test_read_notifications_rejects_invalid_contract(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ReadNotifications.model_validate(payload)


def test_read_notifications_rejects_duplicate_ids_after_uuid_parsing() -> None:
    identifier = uuid4()
    with pytest.raises(ValidationError):
        ReadNotifications.model_validate(
            {"notificationIds": [str(identifier), identifier.hex]}
        )
