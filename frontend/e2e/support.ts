// 실제 서버를 사용하는 E2E의 자원 생성·공고 선택과 실행별 추적 기록입니다.
import { randomUUID } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import process from 'node:process';
import {
  test as base,
  expect,
  type APIRequestContext,
  type Page,
  type Locator,
  type TestInfo,
} from '@playwright/test';
import type { Application } from '../src/features/applications/api';
import type {
  ContestDetail,
  ContestSummary,
} from '../src/features/contests/api';
import type { Profile } from '../src/features/profiles/api';
import type { TeamDetail as Team } from '../src/features/teams/api';
import { verifyEnvironment } from './environment-guard';

export { expect };
export type { Application, Profile, Team };
export type Data<T> = { data: T };
export type Listing<T> = {
  data: T[];
  pagination: {
    total: number;
    page: number;
    pageSize: number;
    totalPages: number;
  };
};
export type TestContest = ContestDetail & { recruitmentDate: string };
export const baseURL = process.env.E2E_BASE_URL ?? '';
export const password = 'Bugbash2026!Synthetic';
export const unique = () => randomUUID().replaceAll('-', '').slice(0, 14);

type Resource = {
  kind: string;
  id: string;
  created: boolean;
  recordedAt: string;
  details: Record<string, unknown>;
};
export type ResourceTracker = {
  runId: string;
  created: (
    kind: 'account' | 'team' | 'application',
    id: string,
    details?: Record<string, unknown>,
  ) => Promise<void>;
  referenced: (
    kind: 'account' | 'team' | 'contest',
    id: string,
    details?: Record<string, unknown>,
  ) => Promise<void>;
};

export const test = base.extend<{ resources: ResourceTracker }>({
  resources: [
    async ({ baseURL }, provide, testInfo) => {
      // 별도 --config나 UI 실행에서도 첫 생성·화면 조작 전에 같은 경계를 확인합니다.
      verifyEnvironment([baseURL], process.env);
      const runId = unique();
      const startedAt = new Date().toISOString();
      const entries: Resource[] = [];
      const path = testInfo.outputPath('resources.json');
      let pendingWrite = Promise.resolve();
      const save = () => {
        const snapshot = JSON.stringify(
          {
            runId,
            startedAt,
            baseURL,
            project: testInfo.project.name,
            test: testInfo.title,
            resources: entries,
          },
          null,
          2,
        );
        pendingWrite = pendingWrite.then(async () => {
          await mkdir(dirname(path), { recursive: true });
          await writeFile(path, snapshot);
        });
        return pendingWrite;
      };
      const record = async (
        created: boolean,
        kind: string,
        id: string,
        details: Record<string, unknown> = {},
      ) => {
        entries.push({
          kind,
          id,
          created,
          recordedAt: new Date().toISOString(),
          details,
        });
        // 이후 화면 조작에 실패해도 이미 생성한 ID를 남깁니다.
        await save();
      };
      await save();
      try {
        await provide({
          runId,
          created: (kind, id, details) => record(true, kind, id, details),
          referenced: (kind, id, details) => record(false, kind, id, details),
        });
      } finally {
        await testInfo.attach('resources', {
          path,
          contentType: 'application/json',
        });
      }
    },
    { auto: true },
  ],
});

export async function get<T>(
  client: APIRequestContext,
  path: string,
): Promise<T> {
  const response = await client.get(`/api/v1${path}`);
  expect(response.status(), path).toBe(200);
  return response.json() as Promise<T>;
}

export async function write(
  client: APIRequestContext,
  method: 'POST' | 'PUT',
  path: string,
  data?: unknown,
) {
  const token = await get<Data<{ csrfToken: string }>>(client, '/auth/csrf');
  return client.fetch(`/api/v1${path}`, {
    method,
    headers: {
      Origin: new URL(baseURL).origin,
      'X-CSRF-Token': token.data.csrfToken,
    },
    data,
  });
}

export async function createAccount(
  client: APIRequestContext,
  resources: ResourceTracker,
  isPublic = false,
) {
  const loginId = `e2e${resources.runId.slice(0, 6)}${unique().slice(0, 8)}`;
  const response = await write(client, 'POST', '/accounts', {
    loginId,
    password,
  });
  expect(response.status()).toBe(201);
  const accountId: string = (await response.json()).data.account.id;
  await resources.created('account', accountId, { loginId });
  const profile = await write(client, 'PUT', '/me/profile', {
    expectedVersion: '0',
    realName: `검증${loginId.slice(-6)}`,
    profileImageCode: null,
    academicStatusCode: null,
    gradeCode: null,
    weeklyAvailabilityCode: null,
    academicUnitId: null,
    experienceState: 'none',
    experienceBody: null,
    introduction: `실제 연동 검증용 가상 사용자입니다. 실행 ${resources.runId}`,
    fieldCodes: ['design'],
    roleCodes: ['design'],
    skillCodes: [],
    portfolio: null,
  });
  expect(profile.status()).toBe(200);
  if (isPublic) {
    const value: Data<Profile> = await profile.json();
    expect(
      (
        await write(client, 'PUT', '/me/profile/visibility', {
          expectedVersion: value.data.version,
          isPublic: true,
        })
      ).status(),
    ).toBe(200);
  }
  return { loginId, accountId };
}

export async function login(
  page: Page,
  loginId: string,
  loginPassword = password,
) {
  await page.goto('/login?returnTo=%2Fprofile');
  await page.getByLabel('아이디', { exact: true }).fill(loginId);
  await page.getByLabel('비밀번호', { exact: true }).fill(loginPassword);
  const response = page.waitForResponse(
    (value) =>
      value.url().endsWith('/auth/login') &&
      value.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  expect((await response).status()).toBe(200);
  await expect(
    page.getByRole('button', { name: '프로필 수정', exact: true }),
  ).toBeVisible();
}

export async function selectContest(
  client: APIRequestContext,
  resources: ResourceTracker,
  capacity = 2,
): Promise<TestContest> {
  // 날짜만 입력하는 UI와 동일하게 내일 한국시간의 종료 경계를 사용합니다.
  const day = 86_400_000;
  const recruitmentDate = new Date(Date.now() + day + 9 * 3_600_000)
    .toISOString()
    .slice(0, 10);
  const deadline = Date.parse(`${recruitmentDate}T00:00:00+09:00`) + day;
  for (let page = 1; ; page += 1) {
    const result = await get<Listing<ContestSummary>>(
      client,
      `/contests?registrationStatus=open&sort=deadline_asc&page=${page}&pageSize=100`,
    );
    for (const summary of result.data) {
      if (summary.isDemo || Date.parse(summary.endsAt) < deadline) continue;
      const { data: contest } = await get<Data<ContestDetail>>(
        client,
        `/contests/${summary.id}`,
      );
      const { kind, minimumMembers, maximumMembers } = contest.capacity;
      if (
        contest.registrationStatus === 'open' &&
        kind !== 'unknown' &&
        (minimumMembers === null ||
          BigInt(minimumMembers) <= BigInt(capacity)) &&
        (maximumMembers === null || BigInt(maximumMembers) >= BigInt(capacity))
      ) {
        await resources.referenced('contest', contest.id, {
          title: contest.title,
          endsAt: contest.endsAt,
          capacity,
          recruitmentDate,
        });
        return { ...contest, recruitmentDate };
      }
    }
    if (page >= result.pagination.totalPages) break;
  }
  throw new Error(
    `기존 개발 DB에 ${capacity}명 정원과 ${recruitmentDate} 한국시간 종료까지 모집을 허용하는 실제 공고가 필요합니다. 공고를 생성하거나 기한을 변경하지 않습니다.`,
  );
}

export async function createTeam(
  client: APIRequestContext,
  contest: TestContest,
  resources: ResourceTracker,
  capacity = 2,
): Promise<Team> {
  const response = await write(client, 'POST', '/teams', {
    requestId: randomUUID(),
    contestId: contest.id,
    name: `E2E팀${resources.runId.slice(0, 6)}${unique().slice(0, 5)}`,
    introduction: `실제 지원과 선발을 검증하는 가상 팀입니다. 실행 ${resources.runId}`,
    capacity: String(capacity),
    roleCodes: capacity === 1 ? [] : ['design'],
    recruitmentDeadline: {
      date: contest.recruitmentDate,
      time: null,
      timeZone: null,
    },
  });
  expect(response.status()).toBe(201);
  const team = ((await response.json()) as Data<Team>).data;
  await resources.created('team', team.id, {
    contestId: contest.id,
    name: team.name,
  });
  return team;
}

// 표시 판정은 실제 응답의 boolean을 사용하며 이름·UUID에서 추정하지 않습니다.
export async function expectDemoBadge(
  scope: Page | Locator,
  kind: 'account' | 'contest' | 'team',
  isDemo: boolean,
) {
  expect(typeof isDemo).toBe('boolean');
  const label = { account: '시연 계정', contest: '시연 공고', team: '시연 팀' }[
    kind
  ];
  const badge = scope.getByText(label, { exact: true });
  await expect(badge).toHaveCount(isDemo ? 1 : 0);
  if (isDemo) await expect(badge).toBeVisible();
}

export async function captureLayout(
  page: Page,
  testInfo: TestInfo,
  name: string,
) {
  await expect
    .poll(
      () =>
        page.evaluate(() => document.documentElement.scrollWidth - innerWidth),
      {
        message: `${name}: 페이지가 가로로 넘치면 안 됩니다`,
      },
    )
    .toBeLessThanOrEqual(1);
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
    animations: 'disabled',
  });
}
