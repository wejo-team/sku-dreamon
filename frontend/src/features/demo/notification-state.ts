/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/notification-state.ts - 알림 발생 기록 원본
 * 2. docs/specs/notifications.md - 지원 상태 변경/신규 지원 두 계열, 발생 건·수신자 중복 방지, 이전 이력 유지
 * 3. docs/api/notifications.md#notification-fields - Notification 필드, eventStatus는 사건 발생 당시 상태,
 *    title·body는 현재 권한으로 구성, 새 kind를 추가하지 않음
 *
 * 화면 확인용 메모리 상태입니다. 수신자·발생 건 키는 서버 내부 정보이며 Notification 응답에는 포함하지 않습니다.
 */

import type { Application } from '@/features/applications/api';
import {
  applicationStatusTitles,
  type DemoDatabase,
  type NotificationRecord,
} from '@/features/demo/fixtures';
import { roleLabel } from '@/features/demo/labels';

type Activity = Pick<DemoDatabase, 'applications' | 'teams' | 'profiles'>;

const teamName = (state: Activity, teamId: string) =>
  state.teams.find((team) => team.id === teamId)?.name ?? '';
const ownerOf = (state: Activity, teamId: string) =>
  state.teams.find((team) => team.id === teamId)?.ownerAccountId;
const nameOf = (state: Activity, accountId: string) =>
  state.profiles.find((item) => item.accountId === accountId)?.realName ?? '';

// [출처 3] 지원 상태 변경 알림(지원자 본인)
function statusRecord(
  state: Activity,
  application: Application,
  eventKey: string,
  id: string,
  occurredAt: string,
): NotificationRecord {
  return {
    id,
    eventKey,
    recipientAccountId: application.applicantAccountId,
    kind: 'application_status_changed',
    applicationId: application.id,
    teamId: application.teamId,
    eventStatus: application.status,
    occurredAt,
    readAt: null,
    title: applicationStatusTitles[application.status],
    body: `${teamName(state, application.teamId)} · ${roleLabel(application.roleCode)} 지원`,
  };
}

// [출처 3] 신규 지원 알림(지원받은 팀장)
function newApplicationRecord(
  state: Activity,
  application: Application,
  eventKey: string,
  id: string,
  occurredAt: string,
): NotificationRecord | null {
  const owner = ownerOf(state, application.teamId);
  if (!owner || owner === application.applicantAccountId) return null;
  return {
    id,
    eventKey,
    recipientAccountId: owner,
    kind: 'new_application',
    applicationId: application.id,
    teamId: application.teamId,
    eventStatus: 'submitted',
    occurredAt,
    readAt: null,
    title: `${nameOf(state, application.applicantAccountId)} 님이 지원했어요`,
    body: `${teamName(state, application.teamId)} · ${roleLabel(application.roleCode)} 지원`,
  };
}

// [출처 2] 실제로 상태가 바뀐 지원마다 수신자별 한 건. 신규 접수는 팀장에게도 한 건
export function transitionNotifications(
  before: Activity,
  after: Activity,
  eventId: string,
  occurredAt: string,
  makeId: () => string = () => crypto.randomUUID(),
): NotificationRecord[] {
  const previous = new Map(before.applications.map((item) => [item.id, item]));
  const result: NotificationRecord[] = [];
  for (const application of after.applications) {
    const old = previous.get(application.id);
    if (old?.status === application.status) continue;
    const key = `${eventId}:${application.id}`;
    result.push(
      statusRecord(
        after,
        application,
        `${key}:applicant`,
        makeId(),
        occurredAt,
      ),
    );
    if (!old && application.status === 'submitted') {
      const leader = newApplicationRecord(
        after,
        application,
        `${key}:leader`,
        makeId(),
        occurredAt,
      );
      if (leader) result.push(leader);
    }
  }
  return result;
}

// [출처 2] 같은 발생 건·수신자 조합은 한 번만 추가하고 이전 읽음 상태를 유지
export function appendNotifications(
  current: NotificationRecord[],
  incoming: NotificationRecord[],
) {
  const keys = new Set(
    current.map((item) => `${item.eventKey}:${item.recipientAccountId}`),
  );
  const additions = incoming.filter((item) => {
    const key = `${item.eventKey}:${item.recipientAccountId}`;
    if (keys.has(key)) return false;
    keys.add(key);
    return true;
  });
  return [...current, ...additions];
}

// [출처 3] 현재 수신자 관계: 본인 알림, 신규 지원은 지금도 그 팀의 팀장일 때만
export function isNotificationRecipient(
  notification: NotificationRecord,
  state: Pick<DemoDatabase, 'teams'>,
  accountId: string,
) {
  if (notification.recipientAccountId !== accountId) return false;
  return (
    notification.kind !== 'new_application' ||
    state.teams.some(
      (team) =>
        team.id === notification.teamId && team.ownerAccountId === accountId,
    )
  );
}

// [출처 2] 가져온 예시 이력: 각 지원의 현재 상태(지원자)와 최초 접수(팀장) 두 계열만.
// 기록된 시각만 사용하며 마감 알림은 만들지 않습니다.
export function historyNotifications(
  state: Activity,
  makeId: (index: number) => string,
): NotificationRecord[] {
  const records: NotificationRecord[] = [];
  for (const application of state.applications) {
    records.push(
      statusRecord(
        state,
        application,
        `history:${application.id}:applicant`,
        makeId(records.length),
        application.updatedAt,
      ),
    );
    const leader = newApplicationRecord(
      state,
      application,
      `history:${application.id}:leader`,
      makeId(records.length),
      application.submittedAt,
    );
    if (leader) records.push(leader);
  }
  return records;
}
