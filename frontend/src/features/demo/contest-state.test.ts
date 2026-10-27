import { describe, expect, it } from 'vitest';
import {
  contestBadgeLabel,
  contestDaysLeft,
  contestStatus,
  deadlineLabel,
  deadlineNotice,
  interpretDeadline,
  memberLimitLabel,
  openingNotice,
  referenceNow,
} from '@/features/demo/contest-state';
import { createDemoRecords, deriveContest } from '@/features/demo/fixtures';

const records = createDemoRecords();
const base = deriveContest(records.contests[0]!, records);

// 마감 입력을 서버 규칙으로 해석해 공고 DTO의 일정에 반영합니다.
const withDeadline = (input: Parameters<typeof interpretDeadline>[0]) => {
  const { endsAt, interpretation } = interpretDeadline(input);
  return {
    ...base,
    endsAt,
    timing: { ...base.timing, endsAt, closing: interpretation },
  };
};

describe('contest registration and closing policies', () => {
  it('only explains opening time defaults reported by the server', () => {
    const exact = {
      ...base.timing,
      openSourceTime: '09:30',
      openSourceTimeZone: 'Asia/Seoul',
      openTimeDefaulted: false,
      openTimeZoneDefaulted: false,
    };
    expect(openingNotice(exact)).toBeNull();
    expect(
      openingNotice({
        ...exact,
        openSourceTimeZone: null,
        openTimeZoneDefaulted: true,
      }),
    ).toBe('원문에 접수 시작 시간대가 없어 한국시간을 적용했어요.');
    const dateOnly = {
      ...exact,
      openSourceTime: null,
      openTimeDefaulted: true,
      openEffectiveTimeZone: 'UTC',
    };
    expect(openingNotice(dateOnly)).toContain('UTC 기준 시작일 00:00');
    expect(openingNotice(dateOnly)).not.toContain('한국시간');
    expect(openingNotice(base.timing)).toContain('시간대도 한국시간으로 보완');
  });

  it('closes a date-only notice at the next midnight in Korea, never at the start of its listed date', () => {
    const contest = withDeadline({ date: '2026-10-18' });
    const boundary = Date.parse('2026-10-18T15:00:00Z');
    expect(contest.endsAt).toBe('2026-10-18T15:00:00Z');
    expect(contestStatus(contest, boundary - 1)).toBe('open');
    expect(contestStatus(contest, boundary)).toBe('closed');
    expect(contestBadgeLabel(contest, referenceNow)).toBe('D-day');
    expect(deadlineNotice(contest.timing.closing)).toContain(
      '서비스 접수 기준',
    );
  });
  it('honors original times and zones and defaults only missing information', () => {
    const timed = interpretDeadline({ date: '2026-10-18', time: '17:30' });
    expect(timed.endsAt).toBe('2026-10-18T08:30:00Z');
    expect(deadlineNotice(timed.interpretation)).toContain(
      '시간대가 없어 한국시간',
    );
    const zoned = interpretDeadline({
      date: '2026-10-18',
      time: '17:30',
      timeZone: 'America/New_York',
    });
    expect(zoned.endsAt).toBe('2026-10-18T21:30:00Z');
    expect(deadlineNotice(zoned.interpretation)).toBeNull();
    expect(
      interpretDeadline({ date: '2026-10-18', timeZone: 'America/New_York' })
        .endsAt,
    ).toBe('2026-10-19T04:00:00Z');
    expect(
      interpretDeadline({
        date: '2026-10-18',
        time: '17:30',
        timeZone: '+02:00',
      }).endsAt,
    ).toBe('2026-10-18T15:30:00Z');
  });
  it('labels UTC and offset times and treats missing limits as unknown', () => {
    const utc = interpretDeadline({
      date: '2026-10-18',
      time: '17:30',
      timeZone: 'UTC',
    });
    expect(deadlineLabel(utc.interpretation)).toBe('2026.10.18 17:30 (UTC)');
    expect(
      contestDaysLeft(
        withDeadline({ date: '2026-10-19', time: '12:00', timeZone: '+02:00' }),
        Date.parse('2026-10-18T17:00:00Z'),
      ),
    ).toBe(1);
    expect(
      memberLimitLabel({
        kind: 'range',
        minimumMembers: '2',
        maximumMembers: null,
      }),
    ).toBe('미확인');
    expect(
      memberLimitLabel({
        kind: 'unlimited',
        minimumMembers: null,
        maximumMembers: null,
      }),
    ).toBe('미확인');
  });
  it('exposes scheduled/open/closed from time rather than a separate publication state', () => {
    const contest = {
      ...withDeadline({ date: '2026-10-20' }),
      startsAt: '2026-10-18T15:00:00Z',
    };
    const start = Date.parse('2026-10-18T15:00:00Z');
    expect(contestStatus(contest, start - 1)).toBe('scheduled');
    expect(contestStatus(contest, start)).toBe('open');
    expect(contestBadgeLabel(contest, start - 1)).toBe('접수 예정');
    expect(deadlineLabel(contest.timing.closing)).toBe('2026.10.20');
  });
  it('keeps one-person, finite, unlimited and unknown capacities distinct', () => {
    expect(
      memberLimitLabel({
        kind: 'range',
        minimumMembers: '1',
        maximumMembers: '1',
      }),
    ).toBe('1명');
    expect(memberLimitLabel(base.capacity)).toBe('2~5명');
    expect(
      memberLimitLabel({
        kind: 'unlimited',
        minimumMembers: '1',
        maximumMembers: null,
      }),
    ).toBe('1명 이상 · 상한 없음');
    expect(
      memberLimitLabel({
        kind: 'unknown',
        minimumMembers: null,
        maximumMembers: null,
      }),
    ).toBe('미확인');
  });
});
