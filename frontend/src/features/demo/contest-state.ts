/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/contest-state.ts - 공고 접수 상태 원본
 * 2. docs/specs/contests.md - 접수 예정/중/마감, 원문 시각·시간대 우선, 누락 시 KST 날짜 종료
 * 3. docs/api/contests.md#contest-timing, #deadline-interpretation - endsAt(제외 경계)과 원문·보완 정보 분리
 * 4. docs/api/teams.md#deadline-input - DeadlineInput을 서버가 원문 우선 정책으로 UTC 경계와 보완 정보로 계산
 * 5. docs/api/contests.md#participation-capacity - ParticipationCapacity 조합
 * 6. docs/design/screens.md - 「재현 경로」 현재 시각은 2026-10-18 고정 예시
 *
 * interpretDeadline은 서버가 할 계산을 목업 서버·픽스처에서 같은 규칙으로 쓰기 위한 함수입니다.
 * 나머지는 API가 준 endsAt·closing·capacity만 읽어 화면 문구를 만듭니다.
 */

import type {
  ContestDetail,
  ContestSummary,
  ContestTiming,
  DeadlineInterpretation,
  ParticipationCapacity,
  RegistrationStatus,
} from '@/features/contests/api';
import type { DeadlineInput } from '@/features/teams/api';
import { MOCK_NOW, appNow } from '@/lib/clock';

// [출처 6] 목업 서버가 쓰는 재현용 고정 현재 시각(운영 시계 아님)
export const referenceNow = MOCK_NOW;
const koreanTimeZone = 'Asia/Seoul';
const dayMs = 86_400_000;

const offsetPattern = /^(?:UTC)?([+-])(\d{2}):?(\d{2})$/i;
const offsetMinutes = (timeZone: string) => {
  if (/^(UTC|Z)$/i.test(timeZone)) return 0;
  const match = timeZone.match(offsetPattern);
  if (!match) return null;
  return (
    (Number(match[2]) * 60 + Number(match[3])) * (match[1] === '-' ? -1 : 1)
  );
};

// 해당 시간대에서 벽시계 시각(년·월·일·시·분·초)에 대응하는 UTC 시각
function zonedInstant(parts: number[], timeZone: string): number {
  const [year, month, day, hour = 0, minute = 0, second = 0] = parts;
  const local = Date.UTC(year!, month! - 1, day!, hour, minute, second);
  const fixed = offsetMinutes(timeZone);
  if (fixed !== null) return local - fixed * 60_000;
  let instant = local;
  const format = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
  for (let attempt = 0; attempt < 3; attempt++) {
    const fields = Object.fromEntries(
      format.formatToParts(instant).map(({ type, value }) => [type, value]),
    );
    const observed = Date.UTC(
      Number(fields.year),
      Number(fields.month) - 1,
      Number(fields.day),
      Number(fields.hour),
      Number(fields.minute),
      Number(fields.second),
    );
    const adjustment = local - observed;
    instant += adjustment;
    if (!adjustment) break;
  }
  return instant;
}

const toTimestamp = (instant: number) =>
  new Date(instant).toISOString().replace('.000Z', 'Z');

// [출처 2, 4] 원문 우선: 시간대가 없으면 한국시간, 시각이 없으면 해당 날짜 끝(다음 날 00:00, 제외 경계)
export function interpretDeadline(input: DeadlineInput): {
  endsAt: string;
  interpretation: DeadlineInterpretation;
} {
  const timeZone = input.timeZone ?? koreanTimeZone;
  const [year, month, day] = input.date.split('-').map(Number);
  let instant: number;
  if (input.time) {
    const [hour, minute, second = 0] = input.time.split(':').map(Number);
    instant = zonedInstant(
      [year!, month!, day!, hour!, minute!, second],
      timeZone,
    );
  } else {
    const next = new Date(Date.UTC(year!, month! - 1, day!) + dayMs);
    instant = zonedInstant(
      [next.getUTCFullYear(), next.getUTCMonth() + 1, next.getUTCDate()],
      timeZone,
    );
  }
  return {
    endsAt: toTimestamp(instant),
    interpretation: {
      sourceDate: input.date,
      sourceTime: input.time ?? null,
      sourceTimeZone: input.timeZone ?? null,
      effectiveTimeZone: timeZone,
      timeDefaulted: !input.time,
      timeZoneDefaulted: !input.timeZone,
    },
  };
}

// [출처 3] 실제 마감 경계는 endsAt
export const contestDeadline = (contest: Pick<ContestDetail, 'endsAt'>) =>
  Date.parse(contest.endsAt);
export const contestStartsAt = (contest: Pick<ContestDetail, 'startsAt'>) =>
  Date.parse(contest.startsAt);

// [출처 2] 접수 예정/중/마감. startsAt 포함, endsAt 제외
export function contestStatus(
  contest: Pick<ContestDetail, 'startsAt' | 'endsAt'>,
  now = appNow(),
): RegistrationStatus {
  if (now >= contestDeadline(contest)) return 'closed';
  return now < contestStartsAt(contest) ? 'scheduled' : 'open';
}
export const isContestOpen = (
  contest: Pick<ContestDetail, 'startsAt' | 'endsAt'>,
  now = appNow(),
) => contestStatus(contest, now) === 'open';

// 시간대 기준 오늘 날짜(YYYY-MM-DD)
function dateIn(timeZone: string, now: number) {
  const fixed = offsetMinutes(timeZone);
  if (fixed !== null)
    return new Date(now + fixed * 60_000).toISOString().slice(0, 10);
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

// [출처 3] D-day: 마감 원문 날짜와 적용 시간대의 오늘 날짜 차이
export function contestDaysLeft(
  contest: Pick<ContestDetail, 'timing'>,
  now = appNow(),
): number {
  const { sourceDate, effectiveTimeZone } = contest.timing.closing;
  const today = dateIn(effectiveTimeZone, now);
  return Math.round((Date.parse(sourceDate) - Date.parse(today)) / dayMs);
}

export function contestBadgeLabel(
  contest: Pick<ContestDetail, 'startsAt' | 'endsAt' | 'timing'>,
  now = appNow(),
): string {
  const status = contestStatus(contest, now);
  if (status === 'scheduled') return '접수 예정';
  if (status === 'closed') return '접수 마감';
  const days = contestDaysLeft(contest, now);
  return days <= 0 ? 'D-day' : `D−${days}`;
}

const zoneLabel = (timeZone: string) => {
  if (/^(UTC|Z)$/i.test(timeZone)) return 'UTC';
  if (offsetPattern.test(timeZone))
    return `UTC${timeZone.replace(/^UTC/i, '')}`;
  return timeZone === koreanTimeZone ? '한국시간' : timeZone;
};

// [출처 3] 원문 마감 표시: 날짜만 있으면 날짜, 시각이 있으면 시각과 시간대
export function deadlineLabel(closing: DeadlineInterpretation): string {
  const date = closing.sourceDate.replaceAll('-', '.');
  if (!closing.sourceTime) return date;
  return `${date} ${closing.sourceTime.slice(0, 5)} (${zoneLabel(closing.effectiveTimeZone)})`;
}

// ─── 목록 요약(ContestSummary) 기준 표시 ────────────────────────
// 접수 상태는 서버가 계산한 registrationStatus를 그대로 쓰고, 날짜만 endsAt(제외 경계)에서 읽습니다.

/** 마지막 접수일(한국시간 YYYY.MM.DD). endsAt은 제외 경계라 직전 순간의 날짜입니다. */
export const endsAtLabel = (endsAt: string) =>
  dateIn(koreanTimeZone, Date.parse(endsAt) - 1).replaceAll('-', '.');

export function summaryDaysLeft(
  contest: Pick<ContestSummary, 'endsAt'>,
  now = appNow(),
): number {
  const lastDay = dateIn(koreanTimeZone, Date.parse(contest.endsAt) - 1);
  const today = dateIn(koreanTimeZone, now);
  return Math.round((Date.parse(lastDay) - Date.parse(today)) / dayMs);
}

export function summaryBadgeLabel(
  contest: Pick<ContestSummary, 'registrationStatus' | 'endsAt'>,
  now = appNow(),
): string {
  if (contest.registrationStatus === 'scheduled') return '접수 예정';
  if (contest.registrationStatus === 'closed') return '접수 마감';
  const days = summaryDaysLeft(contest, now);
  return days <= 0 ? 'D-day' : `D−${days}`;
}

// [출처 2, 3] 서비스가 보완한 사실 안내
export function deadlineNotice(closing: DeadlineInterpretation): string | null {
  if (!closing.timeDefaulted && !closing.timeZoneDefaulted) return null;
  if (closing.timeDefaulted)
    return `원문에 마감 시각이 없어 ${closing.timeZoneDefaulted ? '한국시간' : zoneLabel(closing.effectiveTimeZone)} 기준 해당 날짜 끝까지 접수하고 다음 날 00:00부터 마감해요. ${closing.timeZoneDefaulted ? '시간대도 한국시간으로 보완했어요. ' : ''}서비스 접수 기준이며 주최 기관의 정확한 마감 시각은 원문을 확인해 주세요.`;
  return '원문에 시간대가 없어 한국시간을 서비스 접수 기준으로 적용했어요. 주최 기관의 정확한 시간대는 원문을 확인해 주세요.';
}

// [출처 3] 시작 시각은 서버가 계산한 값과 보완 여부를 안내하며 재해석하지 않습니다.
export function openingNotice(timing: ContestTiming): string | null {
  if (timing.openTimeDefaulted)
    return `원문에 접수 시작 시각이 없어 ${zoneLabel(timing.openEffectiveTimeZone)} 기준 시작일 00:00으로 계산했어요.${timing.openTimeZoneDefaulted ? ' 시간대도 한국시간으로 보완했어요.' : ''}`;
  if (timing.openTimeZoneDefaulted)
    return '원문에 접수 시작 시간대가 없어 한국시간을 적용했어요.';
  return null;
}

// [출처 5] 공식 인원이 확인되었는지
export function hasConfirmedMemberLimit(capacity: ParticipationCapacity) {
  if (capacity.kind === 'unknown' || !capacity.minimumMembers) return false;
  return capacity.kind === 'unlimited' || !!capacity.maximumMembers;
}

// [출처 5] 공식 인원 조건 문구
export function memberLimitLabel(capacity: ParticipationCapacity): string {
  if (!hasConfirmedMemberLimit(capacity)) return '미확인';
  if (capacity.kind === 'unlimited')
    return `${capacity.minimumMembers}명 이상 · 상한 없음`;
  if (capacity.minimumMembers === capacity.maximumMembers)
    return `${capacity.minimumMembers}명`;
  return `${capacity.minimumMembers}~${capacity.maximumMembers}명`;
}

// 숫자 비교용 공식 최소·최대(없으면 null)
export const capacityBounds = (capacity: ParticipationCapacity) => ({
  min: capacity.minimumMembers ? Number(capacity.minimumMembers) : null,
  max: capacity.maximumMembers ? Number(capacity.maximumMembers) : null,
});
