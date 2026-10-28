import { describe, expect, it } from 'vitest';
import { contests } from './data';
import {
  contestBadgeLabel,
  contestDeadline,
  contestDaysLeft,
  contestStatus,
  deadlineLabel,
  memberLimitLabel,
  referenceNow,
} from './contest-state';

const base = contests[0]!;
describe('contest registration and closing policies', () => {
  it('closes a date-only notice at the next midnight in Korea, never at the start of its listed date', () => {
    const contest = { ...base, deadline: '2026-10-18' };
    const boundary = Date.parse('2026-10-18T15:00:00Z');
    expect(contestDeadline(contest)).toBe(boundary);
    expect(contestStatus(contest, boundary - 1)).toBe('open');
    expect(contestStatus(contest, boundary)).toBe('closed');
    expect(contestBadgeLabel(contest, referenceNow)).toBe('D-day');
  });
  it('honors original times and zones and defaults only missing information', () => {
    const timed = { ...base, deadline: '2026-10-18T17:30:00' };
    expect(contestDeadline(timed)).toBe(Date.parse('2026-10-18T08:30:00Z'));
    const zoned = { ...timed, deadlineTimeZone: 'America/New_York' };
    expect(contestDeadline(zoned)).toBe(Date.parse('2026-10-18T21:30:00Z'));
    expect(
      contestDeadline({
        ...base,
        deadline: '2026-10-18',
        deadlineTimeZone: 'America/New_York',
      }),
    ).toBe(Date.parse('2026-10-19T04:00:00Z'));
    expect(
      contestDeadline({ ...base, deadline: '2026-10-18T17:30:00+02:00' }),
    ).toBe(Date.parse('2026-10-18T15:30:00Z'));
  });
  it('preserves UTC timestamps with milliseconds and treats missing limits as unknown', () => {
    const contest = { ...base, deadline: '2026-10-18T17:30:00.125Z' };
    expect(contestDeadline(contest)).toBe(Date.parse(contest.deadline));
    expect(deadlineLabel(contest)).toBe('2026.10.18 17:30 (UTC)');
    expect(
      contestDaysLeft(
        { ...base, deadline: '2026-10-19T12:00:00+02:00' },
        Date.parse('2026-10-18T17:00:00Z'),
      ),
    ).toBe(1);
    expect(memberLimitLabel({ ...base, maxMembers: undefined })).toBe('미확인');
    expect(
      memberLimitLabel({
        ...base,
        memberLimit: 'unlimited',
        minMembers: undefined,
      }),
    ).toBe('미확인');
  });
  it('exposes upcoming/open/closed from time rather than a separate publication state', () => {
    const contest = { ...base, startsAt: '2026-10-19', deadline: '2026-10-20' };
    const start = Date.parse('2026-10-18T15:00:00Z');
    expect(contestStatus(contest, start - 1)).toBe('upcoming');
    expect(contestStatus(contest, start)).toBe('open');
    expect(contestBadgeLabel(contest, start - 1)).toBe('접수 예정');
    expect(deadlineLabel(contest)).toBe('2026.10.20');
  });
  it('keeps one-person, finite, unlimited and unknown capacities distinct', () => {
    expect(memberLimitLabel({ ...base, minMembers: 1, maxMembers: 1 })).toBe(
      '1명',
    );
    expect(memberLimitLabel(base)).toBe('2~5명');
    expect(
      memberLimitLabel({
        ...base,
        memberLimit: 'unlimited',
        minMembers: 1,
        maxMembers: undefined,
      }),
    ).toBe('1명 이상 · 상한 없음');
    expect(
      memberLimitLabel({
        ...base,
        memberLimit: 'unknown',
        minMembers: undefined,
        maxMembers: undefined,
      }),
    ).toBe('미확인');
  });
});
