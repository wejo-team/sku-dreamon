import type { Applicant, Application, ApplicationStatus, Team } from './data';
import type { TeamActivity } from './team-state';

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
