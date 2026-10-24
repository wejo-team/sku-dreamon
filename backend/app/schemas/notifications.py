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
    """본인 알림의 사건 발생 당시 정보와 읽음 상태."""

    id: UUID = Field(description="알림의 UUID.")
    kind: Literal["application_status_changed", "new_application"] = Field(
        description=(
            "알림 종류. "
            "application_status_changed는 지원 "
            "상태 변경, new_application은 팀장이 받은 "
            "신규 지원입니다."
        )
    )
    application_id: UUID = Field(description="알림 사건과 연결된 지원의 UUID.")
    team_id: UUID = Field(description="알림 사건과 연결된 팀의 UUID.")
    event_status: Literal[
        "submitted", "reviewing", "selected", "rejected", "canceled", "discarded"
    ] = Field(
        description=("사건 발생 당시의 지원 상태. 지원의 현재 상태와 다를 수 있습니다.")
    )
    occurred_at: Timestamp = Field(
        description="알림 사건이 실제 발생한 시각. UTC 기준입니다."
    )
    read_at: Timestamp | None = Field(
        description=(
            "최초 읽음 시각. 미읽음이면 null이며 다시 읽어도 최초 시각을 유지합니다."
        )
    )
    title: str = Field(description="현재 조회 권한에 맞춰 구성한 알림 제목.")
    body: str = Field(description="현재 조회 권한에 맞춰 구성한 알림 본문.")


class NotificationPage(Page[NotificationResponse]):
    """본인 알림 목록과 전체 미읽음 수를 함께 제공하는 페이지."""

    unread_count: NonnegativeInt = Field(
        description=("목록 필터와 페이지에 관계없는 본인의 전체 미읽음 알림 수.")
    )


class UnreadCount(ResponseDTO):
    """본인의 전체 미읽음 알림 수."""

    unread_count: NonnegativeInt = Field(description="본인의 전체 미읽음 알림 수.")


class ReadNotifications(RequestDTO):
    """명시한 본인 알림들을 함께 읽음 처리하는 요청."""

    notification_ids: Annotated[
        list[UUID],
        Field(
            min_length=1,
            description=(
                "사용자에게 제공된 알림 중 읽음 처리할 UUID 목록. "
                "최소 1개이며 중복을 허용하지 않습니다."
            ),
        ),
    ]

    @field_validator("notification_ids")
    @classmethod
    def require_unique_ids(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Notification IDs must be unique")
        return values


class ReadNotificationsResult(ResponseDTO):
    """읽음 처리한 알림과 처리 후의 전체 미읽음 수."""

    updated_ids: list[UUID] = Field(
        description=(
            "읽음 처리에 성공한 본인 알림 ID 목록. 이미 읽었던 ID도 포함합니다."
        )
    )
    unread_count: NonnegativeInt = Field(
        description="처리 후 본인의 전체 미읽음 알림 수."
    )
