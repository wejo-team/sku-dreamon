/**
 * [참조 출처]
 * 1. docs/api/conventions.md#session-auth - 인증 필요 요청에 세션이 없으면 401 UNAUTHENTICATED
 * 2. docs/api/conventions.md#versioned-action - expectedVersion을 상태 판단보다 먼저 비교, 불일치 409 VERSION_CONFLICT
 * 3. docs/api/conventions.md#versioned-action - 생성 requestId: 첫 201, 같은 본문 재전송 200, 다른 본문 409 REQUEST_ID_REUSED
 *
 * 목업 서버의 메모리 저장소입니다. 새로고침하면 초기 목업으로 돌아가며 다른 브라우저와 공유되지 않습니다.
 */

import {
  createDemoRecords,
  currentMemberships,
  deriveContest,
  deriveTeam,
  mockNow,
  toContestSummary,
  toTeamSummary,
  type DemoDatabase,
} from '@/features/demo/fixtures';
import type { Profile } from '@/features/profiles/api';
import { conflict, fail, notFound } from '@/lib/api-mock/http';

type IdempotentRecord = {
  accountId: string;
  route: string;
  bodyKey: string;
  resourceId: string;
};

type MockState = {
  db: DemoDatabase;
  /** 현재 세션의 계정 ID. 목업에서는 쿠키 대신 메모리에 둡니다. */
  sessionAccountId: string | null;
  idempotency: Map<string, IdempotentRecord>;
  now: number;
  sequence: number;
};

const fresh = (): MockState => ({
  db: createDemoRecords(),
  sessionAccountId: null,
  idempotency: new Map(),
  now: mockNow,
  sequence: 0,
});

export let state: MockState = fresh();

/** 목업 저장소를 초기 상태로 되돌립니다(테스트·개발용). */
export function resetMockDatabase(
  options: { signedIn?: boolean } = {},
): MockState {
  state = fresh();
  if (options.signedIn) state.sessionAccountId = state.db.account.id;
  return state;
}

export const nowIso = () =>
  new Date(state.now + state.sequence * 1000)
    .toISOString()
    .replace('.000Z', 'Z');

// 새 리소스 UUID(v4 형태). 시드 목록에 없으므로 isDemo=false
export function newId() {
  state.sequence += 1;
  return crypto.randomUUID();
}

// [출처 1]
export function requireSession(): string {
  if (!state.sessionAccountId)
    fail(401, 'UNAUTHENTICATED', '로그인이 필요해요.');
  return state.sessionAccountId!;
}

// [출처 2]
export function assertVersion(current: string, expected: string) {
  if (current !== expected)
    conflict(
      'VERSION_CONFLICT',
      '정보가 변경되었습니다. 최신 상태를 확인해 주세요.',
    );
}
export const bumpVersion = (version: string) =>
  (BigInt(version) + 1n).toString();

// [출처 3] 정규화한 초기 입력의 비교 키: 문자열 앞뒤 공백 제거, 객체 키 정렬, undefined 제외
function canonical(value: unknown): unknown {
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value)
        .filter(([, item]) => item !== undefined)
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([key, item]) => [key, canonical(item)]),
    );
  return value;
}
const canonicalKey = (value: unknown) => JSON.stringify(canonical(value));

// [출처 3] 같은 생성 시도 판별: 인증 주체·경로·정규화한 본문
export function idempotent(
  requestId: string,
  accountId: string,
  route: string,
  body: unknown,
): { replayOf: string | null; remember: (resourceId: string) => void } {
  const bodyKey = canonicalKey(body);
  const existing = state.idempotency.get(requestId);
  if (existing) {
    if (
      existing.accountId !== accountId ||
      existing.route !== route ||
      existing.bodyKey !== bodyKey
    )
      conflict('REQUEST_ID_REUSED', '같은 요청 ID를 다른 내용에 사용했어요.');
    return { replayOf: existing.resourceId, remember: () => {} };
  }
  return {
    replayOf: null,
    remember: (resourceId) =>
      state.idempotency.set(requestId, {
        accountId,
        route,
        bodyKey,
        resourceId,
      }),
  };
}

export const db = () => state.db;

export function profileOf(accountId: string): Profile | undefined {
  return state.db.profiles.find((item) => item.accountId === accountId);
}

export function contestById(contestId: string) {
  const seed = state.db.contests.find((item) => item.id === contestId);
  return seed ? deriveContest(seed, state.db, state.now) : undefined;
}

export const contestSummaries = () =>
  state.db.contests.map((seed) =>
    toContestSummary(deriveContest(seed, state.db, state.now)),
  );

export function teamById(teamId: string) {
  const record = state.db.teams.find((item) => item.id === teamId);
  return record ? deriveTeam(record, state.db, state.now) : undefined;
}

export function teamRecord(teamId: string) {
  return state.db.teams.find((item) => item.id === teamId) ?? notFound();
}

export const teamSummary = (teamId: string) => toTeamSummary(teamById(teamId)!);

export const isCurrentMember = (teamId: string, accountId: string) =>
  currentMemberships(state.db.memberships, teamId).some(
    (item) => item.accountId === accountId,
  );

export function catalogHas(
  list: keyof Omit<DemoDatabase['catalogs'], never>,
  code: string,
) {
  return state.db.catalogs[list].some(
    (item) => item.code === code && item.isSelectable,
  );
}
