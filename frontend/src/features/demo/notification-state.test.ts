import { describe, expect, it } from 'vitest';
import type { Application } from '@/features/applications/api';
import { createDemoRecords, demoIds } from '@/features/demo/fixtures';
import {
  appendNotifications,
  historyNotifications,
  isNotificationRecipient,
  transitionNotifications,
} from '@/features/demo/notification-state';

const { accounts, teams } = demoIds;
const records = createDemoRecords();
const before = { ...records, applications: [] };
const application: Application = {
  id: 'new-application',
  version: '1',
  teamId: teams.makers,
  contestId: demoIds.contests.campus,
  applicantAccountId: accounts.me,
  roleCode: 'planning',
  message: null,
  status: 'submitted',
  discardReason: null,
  discardedByApplicationId: null,
  discardedByTeamId: null,
  submittedAt: '2026-10-19T05:00:00Z',
  updatedAt: '2026-10-19T05:00:00Z',
};
const applied = { ...before, applications: [application] };
const occurredAt = '2026-10-19T05:00:00Z';
const withStatus = (status: Application['status']) => ({
  ...applied,
  applications: [{ ...application, status }],
});

describe('notification occurrence history', () => {
  it('creates one item for each actual recipient relationship and deduplicates the same occurrence', () => {
    const arrival = transitionNotifications(
      before,
      applied,
      'apply-1',
      occurredAt,
    );
    expect(arrival).toHaveLength(2);
    expect(arrival.map((item) => [item.recipientAccountId, item.kind])).toEqual(
      [
        [accounts.me, 'application_status_changed'],
        [accounts.minjun, 'new_application'],
      ],
    );
    expect(
      arrival.every((item) => item.occurredAt === occurredAt && !item.readAt),
    ).toBe(true);
    const read = arrival.map((item) => ({ ...item, readAt: occurredAt }));
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
    ).map((item) => ({ ...item, readAt: occurredAt }));
    const reviewing = withStatus('reviewing');
    const selected = withStatus('selected');
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
      history
        .slice(2)
        .map((item) => [item.eventStatus, item.readAt, item.kind]),
    ).toEqual([
      ['reviewing', null, 'application_status_changed'],
      ['selected', null, 'application_status_changed'],
    ]);
  });

  it('creates separate new-application occurrences after cancellation and does not notify the leader about cancellation', () => {
    const canceled = withStatus('canceled');
    const cancellation = transitionNotifications(
      applied,
      canceled,
      'cancel-1',
      occurredAt,
    );
    expect(cancellation).toHaveLength(1);
    expect(cancellation[0]?.kind).toBe('application_status_changed');
    const reapplied = {
      ...canceled,
      applications: [
        ...canceled.applications,
        { ...application, id: 'reapplication' },
      ],
    };
    const second = transitionNotifications(
      canceled,
      reapplied,
      'apply-2',
      occurredAt,
    );
    expect(second).toHaveLength(2);
    expect(
      second.every(
        (item) => item.applicationId === 'reapplication' && !item.readAt,
      ),
    ).toBe(true);
  });

  it('only exposes items whose recipient relationship still belongs to the viewer', () => {
    const arrival = transitionNotifications(
      before,
      applied,
      'apply-1',
      occurredAt,
    );
    expect(
      arrival.filter((item) =>
        isNotificationRecipient(item, records, accounts.me),
      ),
    ).toHaveLength(1);
    expect(
      arrival.filter((item) =>
        isNotificationRecipient(item, records, accounts.minjun),
      ),
    ).toHaveLength(1);
    // 팀장이 바뀐 뒤에는 이전 팀장에게 신규 지원 알림을 보여주지 않음
    const transferred = {
      teams: records.teams.map((team) =>
        team.id === teams.makers
          ? { ...team, ownerAccountId: accounts.doyun }
          : team,
      ),
    };
    expect(
      arrival.filter((item) =>
        isNotificationRecipient(item, transferred, accounts.minjun),
      ),
    ).toHaveLength(0);
  });

  it('imports only two notification families, without inventing timestamps or deadline events', () => {
    const history = historyNotifications(
      records,
      (index) => `history-${index}`,
    );
    const ownedElsewhere = records.applications.filter(
      (item) =>
        records.teams.find((team) => team.id === item.teamId)
          ?.ownerAccountId !== item.applicantAccountId,
    );
    expect(history).toHaveLength(
      records.applications.length + ownedElsewhere.length,
    );
    expect(new Set(history.map((item) => item.kind))).toEqual(
      new Set(['application_status_changed', 'new_application']),
    );
    const recorded = new Set(
      records.applications.flatMap((item) => [
        item.submittedAt,
        item.updatedAt,
      ]),
    );
    expect(history.every((item) => recorded.has(item.occurredAt))).toBe(true);
  });
});
