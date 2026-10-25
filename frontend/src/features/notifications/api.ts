/**
 * [참조 출처]
 * 1. docs/api/notifications.md#notification-endpoints - GET /me/notifications, GET /me/notifications/unread-count,
 *    PUT /me/notifications/{notificationId}/read, PUT /me/notifications/read
 * 2. docs/api/notifications.md#notification-fields - NotificationPage, Notification, UnreadCount, ReadNotifications, ReadNotificationsResult
 * 3. docs/api/conventions.md#success-responses - NotificationPage는 Page<Notification> 전체 + unreadCount, 다시 감싸지 않음
 */

import { z } from 'zod';
import { apiRequest, withQuery } from '@/lib/api';
import {
  Id,
  PageMeta,
  SafeInteger,
  Timestamp,
  success,
} from '@/lib/api-contract';
import { ApplicationStatus } from '@/features/applications/api';

// [출처 2]
export const NotificationKind = z.enum([
  'application_status_changed',
  'new_application',
]);
export type NotificationKind = z.infer<typeof NotificationKind>;

export const Notification = z
  .object({
    id: Id,
    kind: NotificationKind,
    applicationId: Id,
    teamId: Id,
    eventStatus: ApplicationStatus,
    occurredAt: Timestamp,
    readAt: Timestamp.nullable(),
    title: z.string(),
    body: z.string(),
  })
  .strict();
export type Notification = z.infer<typeof Notification>;

// [출처 2, 3] data·pagination·unreadCount가 같은 객체의 최상위
export const NotificationPage = z
  .object({
    data: z.array(Notification),
    pagination: PageMeta,
    unreadCount: SafeInteger,
  })
  .strict();
export type NotificationPage = z.infer<typeof NotificationPage>;

export const UnreadCount = z.object({ unreadCount: SafeInteger }).strict();
export type UnreadCount = z.infer<typeof UnreadCount>;

// [출처 2] 최소 1개, 중복 없음
export const ReadNotifications = z
  .object({
    notificationIds: z
      .array(Id)
      .min(1)
      .refine((ids) => new Set(ids).size === ids.length, '중복 ID'),
  })
  .strict();
export type ReadNotifications = z.infer<typeof ReadNotifications>;

export const ReadNotificationsResult = z
  .object({ updatedIds: z.array(Id), unreadCount: SafeInteger })
  .strict();
export type ReadNotificationsResult = z.infer<typeof ReadNotificationsResult>;

export type NotificationListQuery = {
  page?: number;
  pageSize?: number;
  unreadOnly?: boolean;
};

// [출처 1] GET /me/notifications → 200 NotificationPage. 열기만으로 읽음 처리하지 않음
export async function listMyNotifications(
  query: NotificationListQuery = {},
  signal?: AbortSignal,
) {
  return NotificationPage.parse(
    await apiRequest(withQuery('/me/notifications', query), { signal }),
  );
}

// [출처 1] GET /me/notifications/unread-count → 200 Success<UnreadCount>
export async function getUnreadNotificationCount(signal?: AbortSignal) {
  return success(UnreadCount).parse(
    await apiRequest('/me/notifications/unread-count', { signal }),
  ).data;
}

// [출처 1] PUT /me/notifications/{notificationId}/read → 200 Success<Notification>
export async function readNotification(
  notificationId: string,
  signal?: AbortSignal,
) {
  return success(Notification).parse(
    await apiRequest(
      `/me/notifications/${encodeURIComponent(notificationId)}/read`,
      { method: 'PUT', signal },
    ),
  ).data;
}

// [출처 1, 2] PUT /me/notifications/read → 200 Success<ReadNotificationsResult>. 하나라도 타인·없는 ID면 404로 전체 실패
export async function readNotifications(
  body: ReadNotifications,
  signal?: AbortSignal,
) {
  const response = await apiRequest('/me/notifications/read', {
    method: 'PUT',
    json: ReadNotifications.parse(body),
    signal,
  });
  return success(ReadNotificationsResult).parse(response).data;
}
