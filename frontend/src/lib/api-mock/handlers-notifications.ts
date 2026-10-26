/**
 * [참조 출처]
 * 1. docs/api/notifications.md#notification-endpoints - 본인 알림만, 정렬 occurredAt DESC, id DESC, 타인·없는 ID 404
 * 2. docs/api/notifications.md#notification-fields - NotificationPage.unreadCount는 필터와 무관한 전체 미읽음 수,
 *    여러 ID 읽음은 전부 성공 또는 전부 실패, 이미 읽은 항목은 최초 readAt 유지
 *
 * AI API는 docs/api/ai.md에서 미구현·SSE 검토안이므로 목업 서버에 경로를 두지 않습니다.
 */

import { ReadNotifications } from '@/features/notifications/api';
import {
  toNotificationDto,
  type NotificationRecord,
} from '@/features/demo/fixtures';
import {
  MockRouter,
  booleanQuery,
  notFound,
  ok,
  paginate,
  validate,
} from '@/lib/api-mock/http';
import { db, nowIso, requireSession } from '@/lib/api-mock/state';

const toNotification = (record: NotificationRecord) =>
  toNotificationDto(record);

const mine = (accountId: string) =>
  db().notifications.filter((item) => item.recipientAccountId === accountId);
const unreadCount = (accountId: string) =>
  mine(accountId).filter((item) => !item.readAt).length;

function markRead(ids: string[], accountId: string) {
  const owned = new Set(mine(accountId).map((item) => item.id));
  // [출처 2] 하나라도 타인·없는 ID면 전체 변경 없이 404
  if (ids.some((id) => !owned.has(id))) notFound();
  const readAt = nowIso();
  db().notifications = db().notifications.map((item) =>
    ids.includes(item.id) && !item.readAt ? { ...item, readAt } : item,
  );
}

export function registerNotificationRoutes(router: MockRouter) {
  router
    // [출처 1, 2]
    .on('GET', '/me/notifications', ({ query }) => {
      const accountId = requireSession();
      const unreadOnly = booleanQuery(query, 'unreadOnly');
      const items = mine(accountId)
        .filter((item) => !unreadOnly || !item.readAt)
        .sort(
          (left, right) =>
            right.occurredAt.localeCompare(left.occurredAt) ||
            right.id.localeCompare(left.id),
        )
        .map(toNotification);
      return new Response(
        JSON.stringify({
          ...paginate(items, query),
          unreadCount: unreadCount(accountId),
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    })
    .on('GET', '/me/notifications/unread-count', () =>
      ok({ unreadCount: unreadCount(requireSession()) }),
    )
    .on('PUT', '/me/notifications/{notificationId}/read', ({ params }) => {
      const accountId = requireSession();
      markRead([params.notificationId!], accountId);
      return ok(
        toNotification(
          mine(accountId).find((item) => item.id === params.notificationId)!,
        ),
      );
    })
    .on('PUT', '/me/notifications/read', ({ body }) => {
      const accountId = requireSession();
      const input = validate(ReadNotifications, body);
      markRead(input.notificationIds, accountId);
      return ok({
        updatedIds: input.notificationIds,
        unreadCount: unreadCount(accountId),
      });
    });
}
