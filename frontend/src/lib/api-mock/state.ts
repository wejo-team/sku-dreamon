/**
 * [참조 출처]
 * 1. docs/api/conventions.md#session-auth - 인증 필요 요청에 세션이 없으면 401 UNAUTHENTICATED
 * 2. docs/api/conventions.md#versioned-action - expectedVersion을 상태 판단보다 먼저 비교, 불일치 409 VERSION_CONFLICT
 * 3. docs/api/conventions.md#versioned-action - 생성 requestId: 첫 201, 같은 본문 재전송 200, 다른 본문 409 REQUEST_ID_REUSED
 * 4. docs/api/notifications.md#notification-fields - 성공한 업무 변경에서 지원 상태 변경/신규 지원 알림 생성
 * 5. docs/specs/notifications.md - 지원자 본인에게 상태 변경, 신규 지원은 팀장에게도 알림
 *
 * 목업 서버의 메모리 저장소입니다. 새로고침하면 초기 목업으로 돌아가며 다른 브라우저와 공유되지 않습니다.
 */

import {
  applicationStatusTitles,
  createDemoRecords,
  currentMemberships,
  deriveContest,
  deriveTeam,
  mockNow,
  toContestSummary,
  toTeamSummary,
  type DemoDatabase,
} from '@/features/demo/fixtures';
import type { Application } from '@/features/applications/api';
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

// [출처 3] 같은 생성 시도 판별: 인증 주체·경로·정규화한 본문
export function idempotent(
  requestId: string,
  accountId: string,
  route: string,
  body: unknown,
): { replayOf: string | null; remember: (resourceId: string) => void } {
  const bodyKey = JSON.stringify(body);
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

// 같은 공모전의 현재 확정 소속
export const hasMembershipInContest = (contestId: string, accountId: string) =>
  state.db.memberships.some(
    (item) =>
      !item.endedAt &&
      item.accountId === accountId &&
      state.db.teams.find((team) => team.id === item.teamId)?.contestId ===
        contestId,
  );

export function catalogHas(
  list: keyof Omit<DemoDatabase['catalogs'], never>,
  code: string,
) {
  return state.db.catalogs[list].some(
    (item) => item.code === code && item.isSelectable,
  );
}

export function roleLabel(code: string) {
  return (
    state.db.catalogs.roles.find((item) => item.code === code)?.displayName ??
    code
  );
}

// [출처 4, 5] 지원 상태 변경 알림. 신규 지원은 팀장에게 new_application도 보냅니다.
export function notifyApplication(application: Application, isNew = false) {
  const team = teamById(application.teamId);
  if (!team) return;
  const occurredAt = nowIso();
  const body = `${team.name} · ${roleLabel(application.roleCode)} 지원`;
  state.db.notifications.push({
    id: newId(),
    recipientAccountId: application.applicantAccountId,
    kind: 'application_status_changed',
    applicationId: application.id,
    teamId: team.id,
    eventStatus: application.status,
    occurredAt,
    readAt: null,
    title: applicationStatusTitles[application.status],
    body,
  });
  if (isNew) {
    const name = profileOf(application.applicantAccountId)?.realName ?? '';
    state.db.notifications.push({
      id: newId(),
      recipientAccountId: team.ownerAccountId,
      kind: 'new_application',
      applicationId: application.id,
      teamId: team.id,
      eventStatus: application.status,
      occurredAt,
      readAt: null,
      title: `${name} 님이 지원했어요`,
      body,
    });
  }
}
