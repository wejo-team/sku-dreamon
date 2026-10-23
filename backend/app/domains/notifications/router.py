"""로그인한 본인의 알림 목록과 미읽음 수를 제공한다."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Success
from app.domains.auth.dependencies import CurrentAccount
from app.domains.notifications import service
from app.domains.notifications.schemas import NotificationPage, UnreadCount

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
