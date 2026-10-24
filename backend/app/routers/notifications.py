"""로그인한 본인의 알림 목록과 미읽음 수를 제공한다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Success
from app.dependencies.auth import CurrentAccount, get_current_account
from app.dependencies.csrf import require_csrf
from app.schemas.notifications import (
    NotificationPage,
    NotificationResponse,
    ReadNotifications,
    ReadNotificationsResult,
    UnreadCount,
)
from app.services import notifications as service

router = APIRouter(
    prefix="/me/notifications",
    tags=["notifications"],
    responses=error_responses(401, 500, 503),
)


@router.get("", response_model=NotificationPage, responses=error_responses(422))
async def get_notifications(
    account_id: CurrentAccount,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1, le=9007199254740991)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
    unread_only: Annotated[bool, Query(alias="unreadOnly")] = False,
) -> NotificationPage:
    return await service.list_notifications(
        session, account_id, page=page, page_size=page_size, unread_only=unread_only
    )


@router.get("/unread-count", response_model=Success[UnreadCount])
async def get_unread_count(
    account_id: CurrentAccount, session: DatabaseSession
) -> Success[UnreadCount]:
    return Success(data=await service.get_unread_count(session, account_id))


@router.put(
    "/read",
    response_model=Success[ReadNotificationsResult],
    responses=error_responses(403, 404, 422),
    dependencies=[Depends(get_current_account), Depends(require_csrf)],
)
async def put_notifications_read(
    payload: ReadNotifications, account_id: CurrentAccount, session: DatabaseSession
) -> Success[ReadNotificationsResult]:
    return Success(
        data=await service.read_notifications(
            session, account_id, payload.notification_ids
        )
    )


@router.put(
    "/{notificationId}/read",
    response_model=Success[NotificationResponse],
    responses=error_responses(403, 404, 422),
    dependencies=[Depends(get_current_account), Depends(require_csrf)],
)
async def put_notification_read(
    notification_id: Annotated[UUID, Path(alias="notificationId")],
    account_id: CurrentAccount,
    session: DatabaseSession,
) -> Success[NotificationResponse]:
    return Success(
        data=await service.read_notification(session, account_id, notification_id)
    )
