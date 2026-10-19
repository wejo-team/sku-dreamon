import type { Contest } from './data';

// Keep dated examples reproducible; callers can supply an instant for boundary checks.
export const referenceNow = Date.parse('2026-10-18T09:00:00Z');
const koreanTimeZone = 'Asia/Seoul';
const dayMs = 86_400_000;
const hasTime = (value: string) => /T\d{2}:\d{2}/.test(value);
const hasOffset = (value: string) => /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
const normalizeDate = (value: string) =>
  value.replace(/^(\d{4})\.(\d{2})\.(\d{2})/, '$1-$2-$3');

function zonedInstant(parts: number[], timeZone: string): number {
  const [year, month, day, hour = 0, minute = 0, second = 0] = parts;
  const local = Date.UTC(year!, month! - 1, day!, hour, minute, second);
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

export function scheduleInstant(
  value: string,
  timeZone = koreanTimeZone,
  endOfDate = false,
): number {
  const normalized = normalizeDate(value);
  if (hasTime(normalized) && hasOffset(normalized))
    return Date.parse(normalized);
  const parts = normalized.split(/[-T:]/).map(Number);
  if (endOfDate && !hasTime(normalized)) {
    const next = new Date(
      Date.UTC(parts[0]!, parts[1]! - 1, parts[2]!) + dayMs,
    );
    return zonedInstant(
      [next.getUTCFullYear(), next.getUTCMonth() + 1, next.getUTCDate()],
      timeZone,
    );
  }
  const fractionalMilliseconds = Math.round(((parts[5] ?? 0) % 1) * 1000);
  if (parts[5] != null) parts[5] = Math.floor(parts[5]);
  return zonedInstant(parts, timeZone) + fractionalMilliseconds;
}

export const contestDeadline = (contest: Contest) =>
  scheduleInstant(contest.deadline, contest.deadlineTimeZone, true);
export const contestStartsAt = (contest: Contest) =>
  scheduleInstant(contest.startsAt, contest.startsAtTimeZone);

export function contestStatus(
  contest: Contest,
  now = referenceNow,
): 'upcoming' | 'open' | 'closed' {
  if (now >= contestDeadline(contest)) return 'closed';
  return now < contestStartsAt(contest) ? 'upcoming' : 'open';
}
export const isContestOpen = (contest: Contest, now = referenceNow) =>
  contestStatus(contest, now) === 'open';

export function contestDaysLeft(contest: Contest, now = referenceNow): number {
  const sourceOffset = contest.deadline.match(/(Z|([+-])(\d{2}):?(\d{2}))$/i);
  const zone = contest.deadlineTimeZone ?? koreanTimeZone;
  const format = new Intl.DateTimeFormat('en-CA', {
    timeZone: zone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  const offsetMinutes =
    sourceOffset?.[1] === 'Z'
      ? 0
      : sourceOffset
        ? (Number(sourceOffset[3]) * 60 + Number(sourceOffset[4])) *
          (sourceOffset[2] === '-' ? -1 : 1)
        : null;
  const current =
    offsetMinutes == null
      ? format.format(now)
      : new Date(now + offsetMinutes * 60_000).toISOString().slice(0, 10);
  const endDate = normalizeDate(contest.deadline).slice(0, 10);
  return Math.round((Date.parse(endDate) - Date.parse(current)) / dayMs);
}

export function contestBadgeLabel(
  contest: Contest,
  now = referenceNow,
): string {
  const status = contestStatus(contest, now);
  if (status === 'upcoming') return '접수 예정';
  if (status === 'closed') return '접수 마감';
  const days = contestDaysLeft(contest, now);
  return days <= 0 ? 'D-day' : `D−${days}`;
}

export function deadlineLabel(contest: Contest): string {
  const value = contest.deadline.replaceAll('-', '.');
  if (!hasTime(contest.deadline)) return value;
  const offset = contest.deadline.match(/(Z|[+-]\d{2}:?\d{2})$/i)?.[0];
  const zone =
    offset === 'Z'
      ? 'UTC'
      : offset
        ? `UTC${offset}`
        : contest.deadlineTimeZone === 'Asia/Seoul'
          ? '한국시간'
          : (contest.deadlineTimeZone ?? '한국시간');
  return `${contest.deadline.slice(0, 10).replaceAll('-', '.')} ${contest.deadline.slice(11, 16)} (${zone})`;
}

export function deadlineNotice(contest: Contest): string | null {
  const missingTime = !hasTime(contest.deadline);
  const missingZone = !contest.deadlineTimeZone && !hasOffset(contest.deadline);
  if (!missingTime && !missingZone) return null;
  if (missingTime)
    return `원문에 마감 시각이 없어 ${contest.deadlineTimeZone ?? '한국시간'} 기준 해당 날짜 끝까지 접수하고 다음 날 00:00부터 마감해요. ${missingZone ? '시간대도 한국시간으로 보완했어요. ' : ''}서비스 접수 기준이며 주최 기관의 정확한 마감 시각은 원문을 확인해 주세요.`;
  return '원문에 시간대가 없어 한국시간을 서비스 접수 기준으로 적용했어요. 주최 기관의 정확한 시간대는 원문을 확인해 주세요.';
}

export function memberLimitLabel(contest: Contest): string {
  if (!hasConfirmedMemberLimit(contest)) return '미확인';
  if (contest.memberLimit === 'unlimited')
    return `${contest.minMembers ?? 1}명 이상 · 상한 없음`;
  if (contest.minMembers === contest.maxMembers)
    return `${contest.minMembers}명`;
  return `${contest.minMembers}~${contest.maxMembers}명`;
}

export function hasConfirmedMemberLimit(contest: Contest): boolean {
  if (
    contest.memberLimit === 'unknown' ||
    !Number.isInteger(contest.minMembers) ||
    contest.minMembers! < 1
  )
    return false;
  return (
    contest.memberLimit === 'unlimited' ||
    (Number.isInteger(contest.maxMembers) &&
      contest.maxMembers! >= contest.minMembers!)
  );
}
