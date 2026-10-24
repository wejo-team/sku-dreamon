"""알림 쓰기를 같은 세션에서 처리하고 읽음 명령의 트랜잭션을 소유한다."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Uuid, any_, bindparam, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.notifications import Notification
from app.queries.notifications import get_notification, get_unread_count
from app.schemas.notifications import NotificationResponse, ReadNotificationsResult


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
        response = await get_notification(session, account_id, notification_id)
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
