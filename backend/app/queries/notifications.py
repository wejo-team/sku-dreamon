"""수신자 범위의 알림·사건을 읽고 같은 스냅샷의 응답을 구성한다."""

from uuid import UUID

from sqlalchemy import BigInteger, RowMapping, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.schemas import PageMeta
from app.models.applications import ApplicationEvent
from app.models.notifications import Notification
from app.schemas.notifications import (
    NotificationPage,
    NotificationResponse,
    UnreadCount,
)


def _notification_response(row: RowMapping) -> NotificationResponse:
    # 프로필·이름을 조회하지 않고 본인에게 전달된 사건의 의미만 표시한다.
    # 과거 알림은 현재 지원 상태 대신 사건 발생 당시 상태를 유지한다.
    if row["kind"] == "new_application":
        title = "새 지원이 도착했습니다."
        body = "팀에 접수된 지원을 확인해 주세요."
    else:
        title = "지원 상태가 변경되었습니다."
        body = {
            "submitted": "지원이 접수되었습니다.",
            "reviewing": "지원 검토가 시작되었습니다.",
            "selected": "팀원으로 선발되었습니다.",
            "rejected": "이번 지원은 미선발 처리되었습니다.",
            "canceled": "지원이 취소되었습니다.",
            "discarded": (
                "팀 생성으로 이 지원이 종료되었습니다."
                if row["reason_code"] == "team_created_elsewhere"
                else "다른 팀 선발로 이 지원이 종료되었습니다."
            ),
        }[row["event_status"]]
    return NotificationResponse.model_validate(
        {
            "id": row["id"],
            "kind": row["kind"],
            "application_id": row["application_id"],
            "team_id": row["team_id"],
            "event_status": row["event_status"],
            "occurred_at": row["occurred_at"],
            "read_at": row["read_at"],
            "title": title,
            "body": body,
        }
    )


async def list_notifications(
    session: AsyncSession,
    account_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
) -> NotificationPage:
    """목록·보정 페이지·전체 미읽음 수를 단일 SQL 스냅샷에서 읽는다."""
    unread = Notification.read_at.is_(None)
    filtered_count = func.count().filter(unread) if unread_only else func.count()
    counts = (
        select(
            filtered_count.label("total"),
            func.count().filter(unread).label("unread_count"),
        )
        .where(Notification.recipient_account_id == account_id)
        .cte("notification_counts")
    )
    total_pages = cast(func.ceil(counts.c.total / page_size), BigInteger)
    paging = select(
        counts.c.total,
        counts.c.unread_count,
        total_pages.label("total_pages"),
        func.greatest(1, func.least(page, total_pages)).label("page"),
    ).cte("notification_paging")
    conditions = [Notification.recipient_account_id == account_id]
    if unread_only:
        conditions.append(unread)
    items = (
        select(
            Notification.notification_id.label("id"),
            Notification.kind,
            ApplicationEvent.application_id,
            ApplicationEvent.team_id,
            ApplicationEvent.to_status.label("event_status"),
            ApplicationEvent.reason_code,
            ApplicationEvent.occurred_at,
            Notification.read_at,
            func.row_number()
            .over(
                order_by=(
                    ApplicationEvent.occurred_at.desc(),
                    Notification.notification_id.desc(),
                )
            )
            .label("row_number"),
        )
        .join(
            ApplicationEvent,
            Notification.event_id == ApplicationEvent.application_event_id,
        )
        .where(*conditions)
        .cte("notification_items")
    )
    offset = (paging.c.page - 1) * page_size
    statement = (
        select(paging, items)
        .select_from(
            paging.outerjoin(
                items,
                and_(
                    items.c.row_number > offset,
                    items.c.row_number <= offset + page_size,
                ),
            )
        )
        .order_by(items.c.row_number)
    )
    rows = (await session.execute(statement)).mappings().all()
    summary = rows[0]
    return NotificationPage(
        data=[_notification_response(row) for row in rows if row["id"] is not None],
        pagination=PageMeta(
            page=int(summary["page"]),
            page_size=page_size,
            total=int(summary["total"]),
            total_pages=int(summary["total_pages"]),
        ),
        unread_count=int(summary["unread_count"]),
    )


async def get_unread_count(session: AsyncSession, account_id: UUID) -> UnreadCount:
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.recipient_account_id == account_id,
            Notification.read_at.is_(None),
        )
    )
    return UnreadCount(unread_count=int(count or 0))


async def get_notification(
    session: AsyncSession, account_id: UUID, notification_id: UUID
) -> NotificationResponse:
    """호출자가 존재·수신 권한을 확인한 알림의 사건 당시 응답을 읽는다."""
    row = (
        (
            await session.execute(
                select(
                    Notification.notification_id.label("id"),
                    Notification.kind,
                    ApplicationEvent.application_id,
                    ApplicationEvent.team_id,
                    ApplicationEvent.to_status.label("event_status"),
                    ApplicationEvent.reason_code,
                    ApplicationEvent.occurred_at,
                    Notification.read_at,
                )
                .join(
                    ApplicationEvent,
                    Notification.event_id == ApplicationEvent.application_event_id,
                )
                .where(
                    Notification.recipient_account_id == account_id,
                    Notification.notification_id == notification_id,
                )
            )
        )
        .mappings()
        .one()
    )
    response = _notification_response(row)
    return response
