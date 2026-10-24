"""알림 조회·행 잠금·저장을 수행하고 저장 행이나 내부 조회 결과를 반환한다."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
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

from app.models.applications import ApplicationEvent
from app.models.notifications import Notification


@dataclass(frozen=True)
class NotificationRecord:
    id: UUID
    kind: str
    application_id: UUID
    team_id: UUID
    event_status: str
    reason_code: str | None
    occurred_at: datetime
    read_at: datetime | None


@dataclass(frozen=True)
class NotificationRows:
    items: list[NotificationRecord]
    page: int
    total: int
    total_pages: int
    unread_count: int


def _record(row: RowMapping) -> NotificationRecord:
    return NotificationRecord(
        id=row["id"],
        kind=row["kind"],
        application_id=row["application_id"],
        team_id=row["team_id"],
        event_status=row["event_status"],
        reason_code=row["reason_code"],
        occurred_at=row["occurred_at"],
        read_at=row["read_at"],
    )


async def list_notifications(
    session: AsyncSession,
    account_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
) -> NotificationRows:
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
    return NotificationRows(
        items=[_record(row) for row in rows if row["id"] is not None],
        page=int(summary["page"]),
        total=int(summary["total"]),
        total_pages=int(summary["total_pages"]),
        unread_count=int(summary["unread_count"]),
    )


async def get_unread_count(session: AsyncSession, account_id: UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.recipient_account_id == account_id,
            Notification.read_at.is_(None),
        )
    )
    return int(count or 0)


async def get_notification(
    session: AsyncSession, account_id: UUID, notification_id: UUID
) -> NotificationRecord:
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
    return _record(row)


async def lock_notifications(
    session: AsyncSession, account_id: UUID, notification_ids: Sequence[UUID]
) -> Sequence[Notification]:
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
    return rows


async def flush_notifications(session: AsyncSession) -> None:
    await session.flush()


async def add_notification(session: AsyncSession, notification: Notification) -> None:
    session.add(notification)
    await session.flush()
