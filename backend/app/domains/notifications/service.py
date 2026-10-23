"""수신자 범위에서 알림과 사건을 조회하고 집계를 한 읽기 시점에 맞춘다."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    RowMapping,
    Uuid,
    and_,
    any_,
    bindparam,
    cast,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import PageMeta
from app.domains.applications.models import ApplicationEvent
from app.domains.notifications.models import Notification
from app.domains.notifications.schemas import (
    NotificationPage,
    NotificationResponse,
    ReadNotificationsResult,
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


async def _mark_owned_notifications(
    session: AsyncSession, account_id: UUID, notification_ids: Sequence[UUID]
) -> None:
    if not notification_ids or len(set(notification_ids)) != len(notification_ids):
        raise ValueError("Notification IDs must be nonempty and unique")
    # UUID 배열을 한 매개변수로 전달해 선택 개수에 따른 SQL 인자 상한을 피한다.
    identifiers = bindparam(
        "notification_ids", list(notification_ids), type_=ARRAY(Uuid())
    )
    rows = (
        await session.scalars(
            select(Notification)
            .where(
                Notification.recipient_account_id == account_id,
                Notification.notification_id == any_(identifiers),
            )
            .order_by(Notification.notification_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(rows) != len(notification_ids):
        raise AppError(404, "RESOURCE_NOT_FOUND", "알림을 찾을 수 없습니다.")
    # 모든 소유자를 확인한 뒤 변경하며 동시 요청도 최초 읽음 시각을 유지한다.
    read_at = datetime.now(UTC)
    for row in rows:
        if row.read_at is None:
            row.read_at = read_at
    await session.flush()


async def read_notification(
    session: AsyncSession, account_id: UUID, notification_id: UUID
) -> NotificationResponse:
    """본인 항목의 최초 읽음 시각을 저장하고 커밋 성공 뒤 결과를 반환한다."""
    try:
        await _mark_owned_notifications(session, account_id, [notification_id])
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
        await session.commit()
        return response
    except Exception:
        await session.rollback()
        raise


async def read_notifications(
    session: AsyncSession, account_id: UUID, notification_ids: Sequence[UUID]
) -> ReadNotificationsResult:
    """제공받은 본인 ID 집합만 원자적으로 읽고 이미 읽은 ID도 결과에 포함한다."""
    try:
        await _mark_owned_notifications(session, account_id, notification_ids)
        count = await get_unread_count(session, account_id)
        response = ReadNotificationsResult(
            updated_ids=list(notification_ids), unread_count=count.unread_count
        )
        await session.commit()
        return response
    except Exception:
        await session.rollback()
        raise
