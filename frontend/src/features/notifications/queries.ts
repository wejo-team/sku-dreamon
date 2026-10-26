/**
 * [참조 출처]
 * 1. docs/api/notifications.md#notification-endpoints - GET /me/notifications(NotificationPage + unreadCount),
 *    PUT /me/notifications/{id}/read, PUT /me/notifications/read(전부 성공 또는 전부 실패)
 * 2. docs/development/frontend.md - 「API와 query」 mutation 성공 시 영향받은 query 무효화
 */

import {
  infiniteQueryOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import {
  listMyNotifications,
  readNotification,
  readNotifications,
} from '@/features/notifications/api';
import { queryKeys } from '@/lib/query-keys';

// [출처 1] 알림함 목록(전체 또는 미읽음만)을 페이지 단위로 받습니다. 응답의 unreadCount는 필터와 무관한 전체 미읽음 수입니다.
export const notificationsQueryOptions = (unreadOnly: boolean) =>
  infiniteQueryOptions({
    queryKey: queryKeys.notifications({ unreadOnly }),
    queryFn: ({ pageParam, signal }) =>
      listMyNotifications(
        { page: pageParam, pageSize: 20, unreadOnly: unreadOnly || undefined },
        signal,
      ),
    initialPageParam: 1,
    getNextPageParam: ({ pagination }) =>
      pagination.page < pagination.totalPages ? pagination.page + 1 : undefined,
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
