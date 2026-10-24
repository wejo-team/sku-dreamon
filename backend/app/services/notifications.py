"""알림 응답과 읽음 정책을 처리하고 쓰기 트랜잭션을 소유한다."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import PageMeta
from app.repositories import notifications as repository
from app.schemas.notifications import (
    NotificationPage,
    NotificationResponse,
    ReadNotificationsResult,
    UnreadCount,
)


def _notification_response(row: repository.NotificationRecord) -> NotificationResponse:
    # 프로필·이름을 조회하지 않고 본인에게 전달된 사건의 의미만 표시한다.
    # 과거 알림은 현재 지원 상태 대신 사건 발생 당시 상태를 유지한다.
    if row.kind == "new_application":
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
                if row.reason_code == "team_created_elsewhere"
                else "다른 팀 선발로 이 지원이 종료되었습니다."
            ),
        }[row.event_status]
    return NotificationResponse.model_validate(
        {
            "id": row.id,
            "kind": row.kind,
            "application_id": row.application_id,
            "team_id": row.team_id,
            "event_status": row.event_status,
            "occurred_at": row.occurred_at,
            "read_at": row.read_at,
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
    """본인의 알림과 미읽음 수를 같은 SQL 스냅샷에서 읽어 응답을 구성한다."""
    rows = await repository.list_notifications(
        session, account_id, page=page, page_size=page_size, unread_only=unread_only
    )
    return NotificationPage(
        data=[_notification_response(row) for row in rows.items],
        pagination=PageMeta(
            page=rows.page,
            page_size=page_size,
            total=rows.total,
            total_pages=rows.total_pages,
        ),
        unread_count=rows.unread_count,
    )


async def get_unread_count(session: AsyncSession, account_id: UUID) -> UnreadCount:
    return UnreadCount(
        unread_count=await repository.get_unread_count(session, account_id)
    )


async def get_notification(
    session: AsyncSession, account_id: UUID, notification_id: UUID
) -> NotificationResponse:
    """호출자가 수신 권한을 확인한 알림의 사건 당시 응답을 구성한다."""
    return _notification_response(
        await repository.get_notification(session, account_id, notification_id)
    )


async def _mark_owned_notifications(
    session: AsyncSession, account_id: UUID, notification_ids: Sequence[UUID]
) -> None:
    if not notification_ids or len(set(notification_ids)) != len(notification_ids):
        raise ValueError("Notification IDs must be nonempty and unique")
    rows = await repository.lock_notifications(session, account_id, notification_ids)
    if len(rows) != len(notification_ids):
        raise AppError(404, "RESOURCE_NOT_FOUND", "알림을 찾을 수 없습니다.")
    # 모든 소유자를 확인한 뒤 변경하며 동시 요청도 최초 읽음 시각을 유지한다.
    read_at = datetime.now(UTC)
    for row in rows:
        if row.read_at is None:
            row.read_at = read_at
    await repository.flush_notifications(session)


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
