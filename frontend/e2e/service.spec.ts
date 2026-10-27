import { randomUUID } from 'node:crypto';
import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test';

// 실제 HTTPS → Vite proxy → FastAPI → PostgreSQL. 요청을 가로채거나 목업하지 않습니다.
const origin = 'https://localhost:5183';
const password = 'Bugbash2026!Synthetic';
const unique = () => randomUUID().replaceAll('-', '').slice(0, 14);
type Data<T> = { data: T };
type Profile = { accountId: string; version: string; isPublic: boolean };
type Team = {
  id: string;
  version: string;
  memberCount: number;
  recruitmentState: 'open' | 'closed';
};
type Application = { id: string; version: string; status: string };

async function get<T>(client: APIRequestContext, path: string): Promise<T> {
  const response = await client.get(`/api/v1${path}`);
  expect(response.ok(), `${path}: ${response.status()}`).toBeTruthy();
  return (await response.json()) as T;
}

async function write(
  client: APIRequestContext,
  method: 'POST' | 'PUT',
  path: string,
  data?: unknown,
) {
  const token = await get<Data<{ csrfToken: string }>>(client, '/auth/csrf');
  return client.fetch(`/api/v1${path}`, {
    method,
    headers: { Origin: origin, 'X-CSRF-Token': token.data.csrfToken },
    data,
  });
}

async function createAccount(client: APIRequestContext, isPublic = false) {
  const loginId = `bash${unique()}`;
  const response = await write(client, 'POST', '/accounts', {
    loginId,
    password,
  });
  expect(response.status()).toBe(201);
  const accountId: string = (await response.json()).data.account.id;
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
    introduction: '실제 연동 검증을 위한 가상 사용자입니다.',
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

async function login(page: Page, loginId: string) {
  await page.goto('/login?returnTo=%2Fprofile');
  await page.getByLabel('아이디', { exact: true }).fill(loginId);
  await page.getByLabel('비밀번호', { exact: true }).fill(password);
  const response = page.waitForResponse(
    (value) =>
      value.url().endsWith('/auth/login') &&
      value.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByRole('button', { name: '프로필 수정' })).toBeVisible();
}

async function contestId(client: APIRequestContext) {
  const result = await get<Data<{ id: string; title: string }[]>>(
    client,
    '/contests?q=Bug%20bash&registrationStatus=open',
  );
  const contest = result.data.find(
    (value) => value.title === 'Bug bash 통합검증 공모전',
  );
  expect(contest, '먼저 bug bash 공고와 시드를 준비하세요.').toBeDefined();
  return contest!.id;
}

async function createTeam(client: APIRequestContext, contest: string) {
  const response = await write(client, 'POST', '/teams', {
    requestId: randomUUID(),
    contestId: contest,
    name: `검증팀${unique().slice(0, 6)}`,
    introduction: '실제 지원과 선발을 검증하는 가상 팀입니다.',
    capacity: '2',
    roleCodes: ['design'],
    recruitmentDeadline: {
      date: new Date(Date.now() + 7 * 86400_000).toISOString().slice(0, 10),
      time: null,
      timeZone: null,
    },
  });
  expect(response.status()).toBe(201);
  return ((await response.json()) as Data<Team>).data;
}

test('가입·프로필 저장·공개 전환·새로고침·로그아웃·재로그인', async ({
  page,
  context,
}, testInfo) => {
  const loginId = `bash${unique()}`;
  await page.goto('/signup');
  await page.getByLabel('아이디 (필수)', { exact: true }).fill(loginId);
  await page.getByLabel('비밀번호 (필수)', { exact: true }).fill(password);
  await page.getByLabel('이름 (필수)', { exact: true }).fill('가입검증사용자');
  await page
    .getByRole('group', { name: /관심 분야/ })
    .getByRole('checkbox', { name: '디자인', exact: true })
    .check();
  await page
    .getByRole('group', { name: /희망 역할/ })
    .getByRole('checkbox', { name: '디자인', exact: true })
    .check();
  const created = page.waitForResponse(
    (value) =>
      value.url().endsWith('/accounts') && value.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
  expect((await created).status()).toBe(201);
  await expect(
    page.getByRole('heading', { name: '가입이 완료됐어요' }),
  ).toBeVisible();
  await page.goto('/profile');
  await expect(page.getByRole('button', { name: '프로필 수정' })).toBeVisible();
  await page.getByRole('button', { name: '프로필 수정' }).click();
  await page
    .getByLabel('자기소개 (선택)')
    .fill('새로고침해도 보존되는 통합검증 소개');
  await page.getByRole('button', { name: '변경사항 저장' }).click();
  await expect(page.getByRole('button', { name: '프로필 수정' })).toBeVisible();
  await page.getByRole('switch', { name: '프로필 공개' }).click();
  await page.getByRole('button', { name: '공개로 전환', exact: true }).click();
  await expect(page.getByRole('switch', { name: '프로필 공개' })).toBeChecked();
  await page.reload();
  await expect(
    page.getByText('새로고침해도 보존되는 통합검증 소개', { exact: true }),
  ).toBeVisible();
  const cookies = await context.cookies();
  const session = cookies.find(
    (cookie) => cookie.name === '__Host-sku-dreamon-session',
  );
  expect(session).toMatchObject({
    secure: true,
    httpOnly: true,
    sameSite: 'Lax',
  });
  await page.screenshot({
    path: testInfo.outputPath('saved-profile.png'),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect
    .poll(async () => (await context.request.get('/api/v1/me')).status())
    .toBe(401);
  await login(page, loginId);
  await expect(
    page.getByText('새로고침해도 보존되는 통합검증 소개', { exact: true }),
  ).toBeVisible();
});

test('팀 생성→지원→팀장 선발→알림 읽음→선발자 취소·팀 공간 권한 종료', async ({
  browser,
  playwright,
}, testInfo) => {
  const setup = await playwright.request.newContext({
    baseURL: origin,
    ignoreHTTPSErrors: true,
  });
  const leader = await createAccount(setup);
  await write(setup, 'POST', '/auth/logout');
  const applicant = await createAccount(setup, true);
  const contest = await contestId(setup);
  await setup.dispose();
  const contexts: BrowserContext[] = [];
  try {
    const leaderContext = await browser.newContext({
      ...testInfo.project.use,
      baseURL: origin,
      ignoreHTTPSErrors: true,
    });
    const applicantContext = await browser.newContext({
      ...testInfo.project.use,
      baseURL: origin,
      ignoreHTTPSErrors: true,
    });
    contexts.push(leaderContext, applicantContext);
    const ownerPage = await leaderContext.newPage();
    const memberPage = await applicantContext.newPage();
    await login(ownerPage, leader.loginId);
    await login(memberPage, applicant.loginId);
    await ownerPage.goto(`/teams/new?contestId=${contest}`);
    const name = `브라우저검증팀${unique().slice(0, 5)}`;
    await ownerPage.getByLabel('팀 이름', { exact: true }).fill(name);
    await ownerPage
      .getByLabel('팀 소개와 목표')
      .fill('지원부터 선발과 취소까지 확인하는 통합테스트 팀입니다.');
    await ownerPage.getByLabel('팀장 포함 총 정원').fill('2');
    await ownerPage
      .getByRole('checkbox', { name: '디자인', exact: true })
      .check();
    await ownerPage
      .getByLabel('팀 모집 마감', { exact: true })
      .fill(new Date(Date.now() + 7 * 86400_000).toISOString().slice(0, 10));
    const creation = ownerPage.waitForResponse(
      (value) =>
        value.url().endsWith('/api/v1/teams') &&
        value.request().method() === 'POST',
    );
    await ownerPage
      .getByRole('button', { name: '팀 만들기', exact: true })
      .click();
    const created = await creation;
    expect(created.status()).toBe(201);
    const team: Team = (await created.json()).data;
    await memberPage.goto(`/teams/${team.id}`);
    await memberPage
      .getByRole('radio', { name: '디자인', exact: true })
      .check();
    await memberPage
      .getByLabel(/팀에 전할 말/)
      .fill('통합테스트에 참여합니다.');
    const submission = memberPage.waitForResponse(
      (value) =>
        value.url().endsWith(`/teams/${team.id}/applications`) &&
        value.request().method() === 'POST',
    );
    await memberPage.getByRole('button', { name: '이 팀에 지원하기' }).click();
    const submitted = await submission;
    expect(submitted.status()).toBe(201);
    const application: Application = (await submitted.json()).data;
    await expect(
      memberPage.getByText('지원이 완료됐어요', { exact: true }),
    ).toBeVisible();
    await ownerPage.goto(`/applicants/${application.id}`);
    await ownerPage.getByRole('button', { name: '이 지원자 선발하기' }).click();
    await ownerPage.getByRole('button', { name: '선발하고 팀원 확정' }).click();
    await expect(ownerPage.getByText(/님이 팀원으로 확정됐어요/)).toBeVisible();
    await memberPage.goto(`/teams/${team.id}?view=space`);
    await expect(
      memberPage.getByRole('heading', { name: '확정된 팀원' }),
    ).toBeVisible();
    await memberPage.screenshot({
      path: testInfo.outputPath('selected-member.png'),
      fullPage: true,
    });
    expect(
      await memberPage.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    const notifications = await get<{
      data: { id: string }[];
      unreadCount: number;
    }>(applicantContext.request, '/me/notifications');
    expect(notifications.unreadCount).toBeGreaterThan(0);
    await memberPage
      .getByRole('button', { name: /^알림, 읽지 않은 알림/ })
      .click();
    const read = memberPage.waitForResponse(
      (value) =>
        value.url().endsWith('/me/notifications/read') &&
        value.request().method() === 'PUT',
    );
    await memberPage
      .getByRole('button', { name: '모두 읽음', exact: true })
      .click();
    expect((await read).status()).toBe(200);
    expect(
      (
        await get<Data<{ unreadCount: number }>>(
          applicantContext.request,
          '/me/notifications/unread-count',
        )
      ).data.unreadCount,
    ).toBe(0);
    await memberPage.getByRole('button', { name: '알림 닫기' }).click();
    await memberPage.goto('/workspace?view=applications');
    await memberPage
      .getByRole('button', { name: '지원 취소', exact: true })
      .click();
    await memberPage
      .getByRole('dialog')
      .getByRole('button', { name: '지원 취소하기' })
      .click();
    await expect
      .poll(async () =>
        (
          await applicantContext.request.get(`/api/v1/teams/${team.id}/space`)
        ).status(),
      )
      .toBe(403);
    await memberPage.goto(`/teams/${team.id}?view=space`);
    await expect(
      memberPage.getByRole('heading', {
        name: '현재 팀원만 팀 공간에 들어갈 수 있어요',
      }),
    ).toBeVisible();
    const current = await get<Data<Team>>(
      leaderContext.request,
      `/teams/${team.id}`,
    );
    expect(current.data.memberCount).toBe(1);
    expect(current.data.recruitmentState).toBe('closed');
    await ownerPage.goto(`/teams/${team.id}?view=space`);
    await ownerPage.getByRole('button', { name: '다시 모집하기' }).click();
    await ownerPage.getByRole('button', { name: '모집 중으로 변경' }).click();
    await expect(
      ownerPage.getByRole('button', { name: '모집 종료', exact: true }),
    ).toBeVisible();
    expect(
      (await get<Data<Team>>(leaderContext.request, `/teams/${team.id}`)).data
        .recruitmentState,
    ).toBe('open');
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test('실제 API의 CSRF·비공개·타인 접근·중복 접수·버전 충돌', async ({
  playwright,
}) => {
  const contexts = await Promise.all(
    [1, 2, 3].map(() =>
      playwright.request.newContext({
        baseURL: origin,
        ignoreHTTPSErrors: true,
      }),
    ),
  );
  const [leader, applicant, outsider] = contexts;
  try {
    await createAccount(leader);
    const account = await createAccount(applicant);
    await createAccount(outsider);
    const team = await createTeam(leader, await contestId(leader));
    expect(
      (await outsider.get(`/api/v1/teams/${team.id}/space`)).status(),
    ).toBe(403);
    expect(
      (await outsider.get(`/api/v1/people/${account.accountId}`)).status(),
    ).toBe(404);
    const body = {
      requestId: randomUUID(),
      roleCode: 'design',
      message: '권한과 멱등성 검증',
    };
    expect(
      (
        await applicant.post(`/api/v1/teams/${team.id}/applications`, {
          data: body,
        })
      ).status(),
    ).toBe(403);
    expect(
      (
        await write(applicant, 'POST', `/teams/${team.id}/applications`, body)
      ).status(),
    ).toBe(409);
    const profile = (await get<Data<Profile>>(applicant, '/me/profile')).data;
    expect(
      (
        await write(applicant, 'PUT', '/me/profile/visibility', {
          expectedVersion: profile.version,
          isPublic: true,
        })
      ).status(),
    ).toBe(200);
    const first = await write(
      applicant,
      'POST',
      `/teams/${team.id}/applications`,
      body,
    );
    expect(first.status()).toBe(201);
    const application: Application = (await first.json()).data;
    const repeated = await write(
      applicant,
      'POST',
      `/teams/${team.id}/applications`,
      body,
    );
    expect(repeated.status()).toBe(200);
    expect((await repeated.json()).data.id).toBe(application.id);
    expect(
      (
        await outsider.get(`/api/v1/applications/${application.id}/applicant`)
      ).status(),
    ).toBe(404);
    const current = (await get<Data<Profile>>(applicant, '/me/profile')).data;
    expect(
      (
        await write(applicant, 'PUT', '/me/profile/visibility', {
          expectedVersion: current.version,
          isPublic: false,
        })
      ).status(),
    ).toBe(200);
    expect(
      (await outsider.get(`/api/v1/people/${account.accountId}`)).status(),
    ).toBe(404);
    expect(
      (
        await leader.get(`/api/v1/applications/${application.id}/applicant`)
      ).status(),
    ).toBe(200);
    expect(
      (
        await write(applicant, 'PUT', '/me/profile/visibility', {
          expectedVersion: current.version,
          isPublic: true,
        })
      ).status(),
    ).toBe(409);
  } finally {
    await Promise.all(contexts.map((context) => context.dispose()));
  }
});
