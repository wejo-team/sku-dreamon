"""본인 알림의 사건 시점 정보와 목록·읽음 전송 계약을 정의한다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.http.schemas import (
    NonnegativeInt,
    Page,
    RequestDTO,
    ResponseDTO,
    Timestamp,
)


class NotificationResponse(ResponseDTO):
    id: UUID
    kind: Literal["application_status_changed", "new_application"]
    application_id: UUID
    team_id: UUID
    event_status: Literal[
        "submitted", "reviewing", "selected", "rejected", "canceled", "discarded"
    ]
    occurred_at: Timestamp
    read_at: Timestamp | None
    title: str
    body: str


class NotificationPage(Page[NotificationResponse]):
    unread_count: NonnegativeInt


class UnreadCount(ResponseDTO):
    unread_count: NonnegativeInt


class ReadNotifications(RequestDTO):
    notification_ids: Annotated[list[UUID], Field(min_length=1)]

    @field_validator("notification_ids")
    @classmethod
    def require_unique_ids(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Notification IDs must be unique")
        return values


class ReadNotificationsResult(ResponseDTO):
    updated_ids: list[UUID]
    unread_count: NonnegativeInt
