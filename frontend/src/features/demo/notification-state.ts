/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/notification-state.ts - 알림 발생 기록 원본
 * 2. docs/specs/notifications.md - 지원 상태 변경/신규 지원 두 계열, 발생 건·수신자 중복 방지, 이전 이력 유지
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import type {
  Applicant,
  Application,
  ApplicationStatus,
  Team,
} from '@/features/demo/data';
import type { TeamActivity } from '@/features/demo/team-state';

type Recipient =
  { kind: 'person'; personId: string } | { kind: 'team-owner'; teamId: string };

export type PreviewNotification = {
  id: string;
  eventId: string;
  recipient: Recipient;
  kind: 'application' | 'applicant';
  applicationId: string;
  teamId: string;
  teamName: string;
  applicantName: string;
  role: string;
  status: ApplicationStatus;
  occurredAt: string | null;
  read: boolean;
};

const recipientKey = (recipient: Recipient) =>
  recipient.kind === 'person'
    ? `person:${recipient.personId}`
    : `team-owner:${recipient.teamId}`;

// [출처 2] 현재 수신자 관계 확인
export function isNotificationRecipient(
  notification: PreviewNotification,
  teams: Team[],
) {
  const recipient = notification.recipient;
  return recipient.kind === 'person'
    ? recipient.personId === 'me'
    : teams.some((team) => team.id === recipient.teamId && team.owner);
}

function activityById(state: TeamActivity) {
  return new Map<string, Application | Applicant>(
    [...state.applications, ...state.applicants].map((item) => [item.id, item]),
  );
}

// [출처 2] 성공한 업무 변경별 생성
export function transitionNotifications(
  before: TeamActivity,
  after: TeamActivity,
  eventId: string,
  occurredAt: string,
): PreviewNotification[] {
  const previous = activityById(before);
  const result: PreviewNotification[] = [];
  for (const item of activityById(after).values()) {
    const old = previous.get(item.id);
    if (old?.status === item.status) continue;
    const team = after.teams.find((candidate) => candidate.id === item.teamId);
    if (!team) continue;
    const recipients: Recipient[] = [
      { kind: 'person', personId: item.personId ?? 'me' },
    ];
    if (!old && item.status === '지원완료')
      recipients.push({ kind: 'team-owner', teamId: team.id });
    for (const recipient of recipients) {
      result.push({
        id: `${eventId}:${item.id}:${recipientKey(recipient)}`,
        eventId: `${eventId}:${item.id}`,
        recipient,
        kind: recipient.kind === 'person' ? 'application' : 'applicant',
        applicationId: item.id,
        teamId: team.id,
        teamName: team.name,
        applicantName: 'name' in item ? item.name : '나',
        role: item.role,
        status: item.status,
        occurredAt,
        read: false,
      });
    }
  }
  return result;
}

// [출처 2] 중복 없이 새 미읽음 추가
export function appendNotifications(
  current: PreviewNotification[],
  incoming: PreviewNotification[],
) {
  const keys = new Set(
    current.map((item) => `${item.eventId}:${recipientKey(item.recipient)}`),
  );
  const additions = incoming.filter((item) => {
    const key = `${item.eventId}:${recipientKey(item.recipient)}`;
    if (keys.has(key)) return false;
    keys.add(key);
    return true;
  });
  return [...current, ...additions];
}

/** Imported demo history has no recorded occurrence time; never invent one. */
export function initialNotifications(
  state: TeamActivity,
): PreviewNotification[] {
  return [
    ...state.applications.map((item): PreviewNotification => ({
      id: `fixture:application:${item.id}`,
      eventId: `fixture:application:${item.id}`,
      recipient: { kind: 'person', personId: item.personId ?? 'me' },
      kind: 'application',
      applicationId: item.id,
      teamId: item.teamId,
      teamName: state.teams.find((team) => team.id === item.teamId)?.name ?? '',
      applicantName: '나',
      role: item.role,
      status: item.status,
      occurredAt: null,
      read: false,
    })),
    ...state.applicants.map((item): PreviewNotification => ({
      id: `fixture:applicant:${item.id}`,
      eventId: `fixture:applicant:${item.id}`,
      recipient: { kind: 'team-owner', teamId: item.teamId },
      kind: 'applicant',
      applicationId: item.id,
      teamId: item.teamId,
      teamName: state.teams.find((team) => team.id === item.teamId)?.name ?? '',
      applicantName: item.name,
      role: item.role,
      status: '지원완료',
      occurredAt: null,
      read: false,
    })),
  ];
}
