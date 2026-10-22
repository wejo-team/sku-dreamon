import { describe, expect, it } from 'vitest';
import {
  initialApplicants,
  initialApplications,
  initialTeams,
  type Application,
} from '@/features/demo/data';
import {
  appendNotifications,
  initialNotifications,
  isNotificationRecipient,
  transitionNotifications,
} from '@/features/demo/notification-state';
import type { TeamActivity } from '@/features/demo/team-state';

const before: TeamActivity = {
  teams: initialTeams,
  applications: [],
  applicants: [],
};
const application: Application = {
  id: 'new-application',
  personId: 'me',
  teamId: 'makers',
  role: '기획',
  message: '',
  status: '지원완료',
};
const applied = { ...before, applications: [application] };
const occurredAt = '2026-10-19T05:00:00.000Z';

describe('notification occurrence history', () => {
  it('creates one item for each actual recipient relationship and deduplicates the same occurrence', () => {
    const arrival = transitionNotifications(
      before,
      applied,
      'apply-1',
      occurredAt,
    );
    expect(arrival).toHaveLength(2);
    expect(arrival.map((item) => item.recipient)).toEqual([
      { kind: 'person', personId: 'me' },
      { kind: 'team-owner', teamId: 'makers' },
    ]);
    expect(
      arrival.every((item) => item.occurredAt === occurredAt && !item.read),
    ).toBe(true);
    const read = arrival.map((item) => ({ ...item, read: true }));
    expect(appendNotifications(read, arrival)).toEqual(read);
    expect(
      transitionNotifications(applied, applied, 'fetch-or-retry', occurredAt),
    ).toEqual([]);
  });

  it('keeps previous read items and creates a new unread item for each status change', () => {
    const arrival = transitionNotifications(
      before,
      applied,
      'apply-1',
      occurredAt,
    ).map((item) => ({ ...item, read: true }));
    const reviewing: TeamActivity = {
      ...applied,
      applications: [{ ...application, status: '검토중' }],
    };
    const selected: TeamActivity = {
      ...reviewing,
      applications: [{ ...application, status: '선발' }],
    };
    const history = appendNotifications(
      appendNotifications(
        arrival,
        transitionNotifications(applied, reviewing, 'review-1', occurredAt),
      ),
      transitionNotifications(reviewing, selected, 'select-1', occurredAt),
    );
    expect(history).toHaveLength(4);
    expect(history.slice(0, 2)).toEqual(arrival);
    expect(
      history.slice(2).map((item) => [item.status, item.read, item.kind]),
    ).toEqual([
      ['검토중', false, 'application'],
      ['선발', false, 'application'],
    ]);
  });

  it('creates separate new-application occurrences after cancellation and does not notify the leader about cancellation', () => {
    const cancelled: TeamActivity = {
      ...applied,
      applications: [{ ...application, status: '지원취소' }],
    };
    const cancellation = transitionNotifications(
      applied,
      cancelled,
      'cancel-1',
      occurredAt,
    );
    expect(cancellation).toHaveLength(1);
    expect(cancellation[0]?.kind).toBe('application');
    const reapplied = {
      ...cancelled,
      applications: [
        ...cancelled.applications,
        { ...application, id: 'reapplication' },
      ],
    };
    const second = transitionNotifications(
      cancelled,
      reapplied,
      'apply-2',
      occurredAt,
    );
    expect(second).toHaveLength(2);
    expect(
      second.every(
        (item) => item.applicationId === 'reapplication' && !item.read,
      ),
    ).toBe(true);
  });

  it('does not duplicate mirrored application/applicant records and only exposes recipients belonging to the viewer', () => {
    const mirrored: TeamActivity = {
      ...applied,
      applicants: [
        { ...application, personId: 'me', name: '김지우', interests: [] },
      ],
    };
    const arrival = transitionNotifications(
      before,
      mirrored,
      'apply-1',
      occurredAt,
    );
    expect(arrival).toHaveLength(2);
    expect(
      arrival.filter((item) => isNotificationRecipient(item, initialTeams)),
    ).toHaveLength(1);
    expect(
      arrival.filter((item) =>
        isNotificationRecipient(
          item,
          initialTeams.map((team) => ({
            ...team,
            owner: team.id === 'makers',
          })),
        ),
      ),
    ).toHaveLength(2);
  });

  it('imports only two notification families, without inventing timestamps or deadline events', () => {
    const history = initialNotifications({
      teams: initialTeams,
      applications: initialApplications,
      applicants: initialApplicants,
    });
    expect(history).toHaveLength(
      initialApplications.length + initialApplicants.length,
    );
    expect(new Set(history.map((item) => item.kind))).toEqual(
      new Set(['application', 'applicant']),
    );
    expect(history.every((item) => item.occurredAt === null)).toBe(true);
  });
});
