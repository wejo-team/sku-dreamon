// 모델 driver만 대체한다. 브라우저·HTTPS·인증·자료 조회·SSE·DB는 실제 경로다.
import { randomUUID } from 'node:crypto';
import type { Page, Response } from '@playwright/test';
import {
  baseURL,
  captureLayout,
  createAccount,
  createTeam,
  expect,
  get,
  selectContest,
  test,
  write,
  type Application,
  type Data,
  type Profile,
} from './support';

const answer =
  '등록된 실제 자료를 확인했습니다. 테스트 모델의 연동 검증 응답입니다.';
const invalidated =
  '정보나 접근 권한이 바뀌어 이전 답변을 지웠어요. 현재 조건으로 다시 요청해 주세요.';

test.beforeAll(() => {
  if (
    process.env.E2E_AI_FIXTURE !== '1' ||
    process.env.E2E_AI_VERIFIED_BASE_URL !== baseURL
  ) {
    throw new Error(
      'AI E2E는 격리 DB를 검증하는 scripts/run_bugbash.py --ai-fixture로 실행하세요.',
    );
  }
});

function responseFor(page: Page, path: string) {
  return page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1${path}`) &&
      response.request().method() === 'POST',
  );
}

async function send(page: Page, content: string) {
  await page.getByRole('textbox', { name: 'AI에게 보낼 메시지' }).fill(content);
  const stream = responseFor(page, '/ai/chat/stream');
  await page.getByRole('button', { name: '메시지 보내기' }).click();
  return stream;
}

function checkStream(response: Response) {
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('text/event-stream');
  expect(response.headers()['cache-control']).toBe('no-store');
  expect(response.request().headers()['x-csrf-token']).toBeTruthy();
  const request = response.request().postDataJSON() as {
    requestId?: string;
    input?: { requestId: string };
  };
  // done 뒤 클라이언트가 reader를 닫으면 Chromium은 response.body를 제공하지
  // 않는다. 스트림을 복제하지 않고 UI 수신 결과와 실제 상태·validation을 검사한다.
  return request.requestId ?? request.input!.requestId;
}

test('일반 대화는 실제 자료로 답하고 복사 전 공개 철회를 다시 확인한다', async ({
  browser,
  resources,
}, testInfo) => {
  const viewer = await browser.newContext({
    ...testInfo.project.use,
    baseURL,
    ignoreHTTPSErrors: true,
    permissions: ['clipboard-read', 'clipboard-write'],
  });
  const person = await browser.newContext({ baseURL, ignoreHTTPSErrors: true });
  try {
    await createAccount(viewer.request, resources);
    const account = await createAccount(person.request, resources, true);
    const profile = (await get<Data<Profile>>(person.request, '/me/profile'))
      .data;
    const page = await viewer.newPage();
    await page.goto('/ai');
    const validated = page.waitForResponse((r) =>
      r.url().endsWith('/validation'),
    );
    const stream = await send(page, `E2E 공개 프로필 ${account.accountId}`);
    const requestId = checkStream(stream);
    expect((await (await validated).json()).data.valid).toBe(true);
    await expect(page.getByText(answer, { exact: true })).toBeVisible();
    const card = page.locator(
      `a[href="/people/${account.accountId}?from=%2Fai"]`,
    );
    await expect(card).toContainText(profile.realName);
    expect(
      (
        await get<Data<{ status: string }>>(
          viewer.request,
          `/ai/requests/${requestId}`,
        )
      ).data.status,
    ).toBe('succeeded');
    await page.getByRole('button', { name: '답변 복사' }).click();
    await expect(
      page.getByText('답변을 복사했어요.', { exact: true }),
    ).toHaveCount(1);
    await captureLayout(page, testInfo, 'ai-chat-real-source');

    expect(
      (
        await write(person.request, 'PUT', '/me/profile/visibility', {
          expectedVersion: profile.version,
          isPublic: false,
        })
      ).status(),
    ).toBe(200);
    const revoked = page.waitForResponse((r) =>
      r.url().endsWith('/validation'),
    );
    await page.getByRole('button', { name: '답변 복사' }).click();
    expect((await (await revoked).json()).data).toEqual({
      valid: false,
      result: null,
    });
    await expect(page.getByText(answer, { exact: true })).toHaveCount(0);
    await expect(card).toHaveCount(0);
    await expect(page.getByText(invalidated, { exact: true })).toBeVisible();
    await testInfo.attach('ai-run.json', {
      body: JSON.stringify({
        requestId,
        purpose: 'chat',
        model: 'fixture',
        providerCalls: 0,
      }),
      contentType: 'application/json',
    });
  } finally {
    await person.close();
    await viewer.close();
  }
});

test('일시적 모델 실패는 같은 입력으로 재시도하고 진행 중 답변은 중단한다', async ({
  browser,
  resources,
}, testInfo) => {
  const context = await browser.newContext({
    ...testInfo.project.use,
    baseURL,
    ignoreHTTPSErrors: true,
  });
  try {
    const account = await createAccount(context.request, resources, true);
    const page = await context.newPage();
    await page.goto('/ai');
    const failed = await send(page, `E2E 재시도 ${account.accountId}`);
    const original = failed.request().postDataJSON() as { requestId: string };
    await expect(
      page.getByRole('button', { name: '다시 시도', exact: true }),
    ).toBeVisible();
    const retried = responseFor(
      page,
      `/ai/requests/${original.requestId}/retries/stream`,
    );
    await page.getByRole('button', { name: '다시 시도', exact: true }).click();
    const stream = await retried;
    expect(stream.request().postDataJSON()).toEqual({
      expectedAttempt: 1,
      input: original,
    });
    checkStream(stream);
    await expect(page.getByText(answer, { exact: true })).toBeVisible();

    expect(
      (
        await get<Data<{ attempt: number; status: string }>>(
          context.request,
          `/ai/requests/${original.requestId}`,
        )
      ).data,
    ).toMatchObject({ attempt: 2, status: 'succeeded' });
    await page.getByRole('button', { name: '새 대화' }).click();
    await expect(page.getByText(answer, { exact: true })).toHaveCount(0);
    const pending = await send(page, `E2E 중단 ${account.accountId}`);
    const input = pending.request().postDataJSON() as { requestId: string };
    await expect(
      page.getByText('등록된 실제 자료를 확인했습니다.', { exact: true }),
    ).toBeVisible();
    await page.getByRole('button', { name: '응답 중지' }).click();
    await expect
      .poll(
        async () =>
          (
            await get<Data<{ status: string }>>(
              context.request,
              `/ai/requests/${input.requestId}`,
            )
          ).data.status,
      )
      .toBe('canceled');
    await expect(
      page.getByRole('button', { name: '같은 내용으로 다시 요청' }),
    ).toBeVisible();
    await expect(page.getByText(answer, { exact: true })).toHaveCount(0);
    await captureLayout(page, testInfo, 'ai-canceled');
  } finally {
    await context.close();
  }
});

test('팀장은 실제 지원을 AI로 검토·추천받고 지원 상태는 그대로 유지된다', async ({
  browser,
  resources,
}, testInfo) => {
  const leader = await browser.newContext({
    ...testInfo.project.use,
    baseURL,
    ignoreHTTPSErrors: true,
  });
  const applicant = await browser.newContext({
    baseURL,
    ignoreHTTPSErrors: true,
  });
  try {
    await createAccount(leader.request, resources);
    await createAccount(applicant.request, resources, true);
    const contest = await selectContest(leader.request, resources);
    const team = await createTeam(leader.request, contest, resources);
    const submitted = await write(
      applicant.request,
      'POST',
      `/teams/${team.id}/applications`,
      {
        requestId: randomUUID(),
        roleCode: 'design',
        message: 'AI E2E 검토용 지원입니다.',
      },
    );
    expect(submitted.status()).toBe(201);
    const application = ((await submitted.json()) as Data<Application>).data;
    await resources.created('application', application.id, { teamId: team.id });
    const profile = (await get<Data<Profile>>(applicant.request, '/me/profile'))
      .data;
    expect(
      (
        await write(applicant.request, 'PUT', '/me/profile/visibility', {
          expectedVersion: profile.version,
          isPublic: false,
        })
      ).status(),
    ).toBe(200);
    const page = await leader.newPage();
    await page.goto(`/applicants/${application.id}`);
    const reviewed = responseFor(
      page,
      `/applications/${application.id}/ai-reviews/stream`,
    );
    await page
      .getByRole('button', { name: 'AI 검토 요청', exact: true })
      .click();
    const reviewId = checkStream(await reviewed);
    const review = page.getByRole('region', { name: 'AI 지원자 검토 결과' });
    await expect(review).toContainText(answer);
    expect(
      (
        await get<Data<{ purpose: string; status: string }>>(
          leader.request,
          `/ai/requests/${reviewId}`,
        )
      ).data,
    ).toMatchObject({ purpose: 'applicant_review', status: 'succeeded' });
    await captureLayout(page, testInfo, 'ai-applicant-review');

    await page.goto(`/teams/${team.id}?view=applicants`);
    const recommended = responseFor(
      page,
      `/teams/${team.id}/applicant-recommendations/stream`,
    );
    await page
      .getByRole('button', { name: 'AI 지원자 추천 요청', exact: true })
      .click();
    const recommendationId = checkStream(await recommended);
    const recommendation = page.getByRole('region', {
      name: 'AI 지원자 추천 결과',
    });
    await expect(recommendation).toContainText(answer);
    expect(
      (
        await get<Data<{ purpose: string; status: string }>>(
          leader.request,
          `/ai/requests/${recommendationId}`,
        )
      ).data,
    ).toMatchObject({
      purpose: 'applicant_recommendation',
      status: 'succeeded',
    });
    await expect(
      recommendation.getByRole('link', { name: '추천 후보 1 지원서 확인' }),
    ).toHaveAttribute('href', `/applicants/${application.id}`);
    expect(
      (
        await get<Data<Application>>(
          applicant.request,
          `/applications/${application.id}`,
        )
      ).data,
    ).toEqual(application);
    await captureLayout(page, testInfo, 'ai-applicant-recommendation');
  } finally {
    await applicant.close();
    await leader.close();
  }
});
