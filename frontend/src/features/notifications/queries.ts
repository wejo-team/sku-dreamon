/**
 * [참조 출처]
 * 1. docs/api/notifications.md#notification-endpoints - GET /me/notifications(NotificationPage + unreadCount),
 *    PUT /me/notifications/{id}/read, PUT /me/notifications/read(전부 성공 또는 전부 실패)
 * 2. docs/development/frontend.md - 「API와 query」 mutation 성공 시 영향받은 query 무효화
 */

import {
  queryOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import {
  listMyNotifications,
  readNotification,
  readNotifications,
  type NotificationListQuery,
} from '@/features/notifications/api';
import { queryKeys } from '@/lib/query-keys';

// [출처 1] 알림함은 최근 알림을 최대 페이지 크기로 받습니다.
export const notificationsQueryOptions = (
  query: NotificationListQuery = { pageSize: 100 },
) =>
  queryOptions({
    queryKey: queryKeys.notifications(query),
    queryFn: ({ signal }) => listMyNotifications(query, signal),
  });

// [출처 1, 2] 단건·여러 건 읽음. 성공하면 알림 목록과 미읽음 수를 다시 받습니다.
export function useReadNotifications() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (ids: string[]): Promise<void> => {
      if (ids.length === 1) await readNotification(ids[0]!);
      else await readNotifications({ notificationIds: ids });
    },
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ['my', 'notifications'] }),
  });
}
