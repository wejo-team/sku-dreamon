// 새 계정·팀만 변경하며 지원 상태·알림·공모전별 소속의 실제 저장을 확인합니다.
import { randomUUID } from 'node:crypto';
import type { APIRequestContext } from '@playwright/test';
import type { NotificationPage } from '../src/features/notifications/api';
import {
  test,
  expect,
  baseURL,
  get,
  write,
  createAccount,
  createTeam,
  selectContest,
  captureLayout,
  type Application,
  type Data,
  type ResourceTracker,
} from './support';

async function submit(
  client: APIRequestContext,
  teamId: string,
  resources: ResourceTracker,
) {
  const response = await write(
    client,
    'POST',
    `/teams/${teamId}/applications`,
    {
      requestId: randomUUID(),
      roleCode: 'design',
      message: `생명주기 검증 ${resources.runId}`,
    },
  );
  expect(response.status()).toBe(201);
  const application: Application = (await response.json()).data;
  await resources.created('application', application.id, {
    teamId,
    accountId: application.applicantAccountId,
  });
  return application;
}

async function changeReview(
  client: APIRequestContext,
  application: Application,
  action: 'review-start' | 'rejection',
) {
  const response = await write(
    client,
    'PUT',
    `/applications/${application.id}/${action}`,
    {
      expectedVersion: application.version,
    },
  );
  expect(response.status()).toBe(200);
  return ((await response.json()) as Data<Application>).data;
}

test('취소 후 새 지원·명시적 검토·미선발·재지원 제한과 알림 중복 방지', async ({
  browser,
  resources,
}, testInfo) => {
  const leader = await browser.newContext({
    ...testInfo.project.use,
    baseURL,
    ignoreHTTPSErrors: true,
  });
  const applicant = await browser.newContext({
    ...testInfo.project.use,
    baseURL,
    ignoreHTTPSErrors: true,
  });
  try {
    const contest = await selectContest(leader.request, resources);
    await createAccount(leader.request, resources);
    await createAccount(applicant.request, resources, true);
    const team = await createTeam(leader.request, contest, resources);
    const first = await submit(applicant.request, team.id, resources);
    const canceled = await write(
      applicant.request,
      'PUT',
      `/applications/${first.id}/cancellation`,
      { expectedVersion: first.version },
    );
    expect(canceled.status()).toBe(200);
    const cancellation = (await canceled.json()).data;
    expect(cancellation).toMatchObject({
      application: { status: 'canceled' },
      membershipEnded: false,
    });
    const application = await submit(applicant.request, team.id, resources);
    expect(application.id).not.toBe(first.id);
    expect(application.status).toBe('submitted');
    const beforeRead = await get<NotificationPage>(
      applicant.request,
      '/me/notifications',
    );
    await get(leader.request, `/applications/${application.id}/applicant`);
    await get(leader.request, `/teams/${team.id}/applicants`);
    expect(
      (
        await get<Data<Application>>(
          applicant.request,
          `/applications/${application.id}`,
        )
      ).data,
    ).toEqual(application);
    expect(
      await get<NotificationPage>(applicant.request, '/me/notifications'),
    ).toEqual(beforeRead);
    const oldSelection = await write(
      leader.request,
      'PUT',
      `/applications/${first.id}/selection`,
      { expectedVersion: cancellation.application.version },
    );
    expect(oldSelection.status()).toBe(409);
    expect((await oldSelection.json()).error.code).toBe(
      'INVALID_APPLICATION_STATE',
    );

    const ownerPage = await leader.newPage();
    await ownerPage.goto(`/teams/${team.id}?view=applicants`);
    await expect(
      ownerPage.locator(`a[href="/applicants/${application.id}"]`),
    ).toBeVisible();
    await expect(
      ownerPage.locator(`a[href="/applicants/${first.id}"]`),
    ).toHaveCount(0);
    await ownerPage.locator(`a[href="/applicants/${application.id}"]`).click();
    await ownerPage
      .getByRole('button', { name: '검토 시작', exact: true })
      .click();
    await expect(
      ownerPage.getByText('검토를 시작했어요.', { exact: true }),
    ).toBeVisible();
    await expect(
      ownerPage.getByRole('button', { name: '검토 시작', exact: true }),
    ).toHaveCount(0);
    await testInfo.attach('review-started', {
      body: await ownerPage.screenshot({ fullPage: true }),
      contentType: 'image/png',
    });
    const reviewing = (
      await get<Data<Application>>(
        leader.request,
        `/applications/${application.id}`,
      )
    ).data;
    expect(reviewing.status).toBe('reviewing');
    await ownerPage
      .getByRole('link', { name: '지원자 관리로', exact: true })
      .click();
    const pendingRow = ownerPage.locator(
      `a[href="/applicants/${application.id}"]`,
    );
    await expect(pendingRow).toContainText('검토 중');
    await pendingRow.click();
    const reviewedNotifications = await get<NotificationPage>(
      applicant.request,
      '/me/notifications',
    );
    expect(
      reviewedNotifications.data.filter(
        (notice) =>
          notice.applicationId === application.id &&
          notice.eventStatus === 'reviewing',
      ),
    ).toHaveLength(1);
    expect(
      await changeReview(leader.request, reviewing, 'review-start'),
    ).toEqual(reviewing);
    expect(
      await get<NotificationPage>(applicant.request, '/me/notifications'),
    ).toEqual(reviewedNotifications);
    const applicantPage = await applicant.newPage();
    await applicantPage.goto('/workspace?view=applications');
    await expect(
      applicantPage.getByText('검토 중', { exact: true }),
    ).toBeVisible();

    await ownerPage
      .getByRole('button', { name: '미선발 처리', exact: true })
      .click();
    const rejectionDialog = ownerPage.getByRole('dialog');
    await expect(
      rejectionDialog.getByText(
        '미선발로 처리하면 이 지원자는 이 팀에 다시 지원할 수 없어요. 기존 지원 기록은 남아요.',
        { exact: true },
      ),
    ).toBeVisible();
    await expect(rejectionDialog.locator(':focus')).toHaveCount(1);
    await expect(
      rejectionDialog.getByRole('button', {
        name: '미선발로 확정',
        exact: true,
      }),
    ).toBeInViewport({ ratio: 1 });
    await expect(
      rejectionDialog.getByRole('button', { name: '돌아가기', exact: true }),
    ).toBeInViewport({ ratio: 1 });
    await testInfo.attach('rejection-confirmation', {
      body: await ownerPage.screenshot(),
      contentType: 'image/png',
    });
    await rejectionDialog
      .getByRole('button', { name: '미선발로 확정', exact: true })
      .click();
    await expect(
      ownerPage.getByText('미선발된 지원서예요.', { exact: true }),
    ).toBeVisible();
    await ownerPage
      .getByRole('link', { name: '지원자 관리로', exact: true })
      .click();
    await expect(
      ownerPage.getByText('현재 지원 중인 지원자가 없어요.', { exact: true }),
    ).toBeVisible();
    await expect(
      ownerPage.locator(`a[href="/applicants/${application.id}"]`),
    ).toHaveCount(0);
    await ownerPage.goto(`/applicants/${application.id}`);
    const rejected = (
      await get<Data<Application>>(
        leader.request,
        `/applications/${application.id}`,
      )
    ).data;
    expect(rejected.status).toBe('rejected');
    await applicantPage.reload();
    await expect(
      applicantPage.getByText('미선발', { exact: true }),
    ).toBeVisible();
    await ownerPage.reload();
    await expect(
      ownerPage.getByText('미선발된 지원서예요.', { exact: true }),
    ).toBeVisible();
    const rejectedNotifications = await get<NotificationPage>(
      applicant.request,
      '/me/notifications',
    );
    expect(
      rejectedNotifications.data.filter(
        (notice) =>
          notice.applicationId === application.id &&
          notice.eventStatus === 'rejected',
      ),
    ).toHaveLength(1);
    expect(await changeReview(leader.request, rejected, 'rejection')).toEqual(
      rejected,
    );
    const retry = await write(
      applicant.request,
      'POST',
      `/teams/${team.id}/applications`,
      { requestId: randomUUID(), roleCode: 'design' },
    );
    expect(retry.status()).toBe(409);
    expect((await retry.json()).error.code).toBe('REAPPLICATION_NOT_ALLOWED');
    const cancelRejected = await write(
      applicant.request,
      'PUT',
      `/applications/${rejected.id}/cancellation`,
      { expectedVersion: rejected.version },
    );
    expect(cancelRejected.status()).toBe(409);
    expect((await cancelRejected.json()).error.code).toBe(
      'INVALID_APPLICATION_STATE',
    );
    expect(
      await get<NotificationPage>(applicant.request, '/me/notifications'),
    ).toEqual(rejectedNotifications);
    expect(
      (
        await get<Data<Application>>(
          applicant.request,
          `/applications/${first.id}`,
        )
      ).data.status,
    ).toBe('canceled');
  } finally {
    await Promise.all([leader.close(), applicant.close()]);
  }
});

test('같은 공고의 다른 대기 지원 폐기·소속 제한·취소 후 새 지원', async ({
  browser,
  resources,
}, testInfo) => {
  const contexts = await Promise.all(
    [1, 2, 3].map(() =>
      browser.newContext({
        ...testInfo.project.use,
        baseURL,
        ignoreHTTPSErrors: true,
      }),
    ),
  );
  const [leaderA, leaderB, applicant] = contexts;
  try {
    const contest = await selectContest(leaderA.request, resources);
    await createAccount(leaderA.request, resources);
    await createAccount(leaderB.request, resources);
    await createAccount(applicant.request, resources, true);
    const teamA = await createTeam(leaderA.request, contest, resources);
    const teamB = await createTeam(leaderB.request, contest, resources);
    const applicationA = await submit(applicant.request, teamA.id, resources);
    const applicationB = await submit(applicant.request, teamB.id, resources);
    const reviewingB = await changeReview(
      leaderB.request,
      applicationB,
      'review-start',
    );
    const selection = await write(
      leaderA.request,
      'PUT',
      `/applications/${applicationA.id}/selection`,
      { expectedVersion: applicationA.version },
    );
    expect(selection.status()).toBe(200);
    const selected: Application = (await selection.json()).data.application;
    expect(selected.status).toBe('selected');
    const discarded = (
      await get<Data<Application>>(
        applicant.request,
        `/applications/${applicationB.id}`,
      )
    ).data;
    expect(discarded).toMatchObject({
      status: 'discarded',
      discardReason: 'selected_elsewhere',
      discardedByApplicationId: selected.id,
    });
    expect(discarded.version).not.toBe(reviewingB.version);
    expect(
      (await applicant.request.get(`/api/v1/teams/${teamA.id}/space`)).status(),
    ).toBe(200);
    expect(
      (await applicant.request.get(`/api/v1/teams/${teamB.id}/space`)).status(),
    ).toBe(403);
    const memberRetry = await write(
      applicant.request,
      'POST',
      `/teams/${teamB.id}/applications`,
      { requestId: randomUUID(), roleCode: 'design' },
    );
    expect(memberRetry.status()).toBe(409);
    expect((await memberRetry.json()).error.code).toBe('MEMBERSHIP_CONFLICT');
    const notices = await get<NotificationPage>(
      applicant.request,
      '/me/notifications',
    );
    expect(
      notices.data.filter(
        (notice) =>
          notice.applicationId === applicationB.id &&
          notice.eventStatus === 'discarded',
      ),
    ).toHaveLength(1);
    const page = await applicant.newPage();
    await page.goto('/workspace?view=applications');
    await expect(page.getByText('폐기', { exact: true })).toBeVisible();
    await expect(
      page.getByText('선발 · 팀원 확정', { exact: true }),
    ).toBeVisible();
    const selectedCard = page
      .locator('.workspace-application-list > li')
      .filter({
        has: page.getByRole('heading', { name: teamA.name, exact: true }),
      });
    await selectedCard
      .getByRole('button', { name: '지원 취소', exact: true })
      .click();
    const cancellationResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/applications/${selected.id}/cancellation`) &&
        response.request().method() === 'PUT',
    );
    await page
      .getByRole('dialog')
      .getByRole('button', { name: '지원 취소하기', exact: true })
      .click();
    const cancellation = await cancellationResponse;
    expect(cancellation.status()).toBe(200);
    expect((await cancellation.json()).data.membershipEnded).toBe(true);
    await expect(page.getByText('지원 취소', { exact: true })).toBeVisible();
    expect(
      (
        await get<Data<Application>>(
          applicant.request,
          `/applications/${discarded.id}`,
        )
      ).data,
    ).toEqual(discarded);
    await page.goto(`/teams/${teamB.id}`);
    await page.getByRole('radio', { name: '디자인', exact: true }).click();
    await page
      .getByLabel(/팀에 전할 말/)
      .fill(`폐기 후 화면 재지원 ${resources.runId}`);
    const newApplicationResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/teams/${teamB.id}/applications`) &&
        response.request().method() === 'POST',
    );
    await page
      .getByRole('button', { name: '이 팀에 지원하기', exact: true })
      .click();
    const created = await newApplicationResponse;
    expect(created.status()).toBe(201);
    const reapplication: Application = (await created.json()).data;
    await resources.created('application', reapplication.id, {
      teamId: teamB.id,
      accountId: reapplication.applicantAccountId,
    });
    await expect(
      page.getByText('지원이 완료됐어요', { exact: true }),
    ).toBeVisible();
    await captureLayout(page, testInfo, 'discarded-reapplication-complete');
    expect(
      (
        await get<Data<Application>>(
          applicant.request,
          `/applications/${discarded.id}`,
        )
      ).data,
    ).toEqual(discarded);
    expect(
      (
        await get<Data<Application>>(
          applicant.request,
          `/applications/${reapplication.id}`,
        )
      ).data,
    ).toEqual(reapplication);
    expect(reapplication.id).not.toBe(discarded.id);
    expect(reapplication.status).toBe('submitted');
    expect(
      (await applicant.request.get(`/api/v1/teams/${teamA.id}/space`)).status(),
    ).toBe(403);
    expect(
      (await applicant.request.get(`/api/v1/teams/${teamB.id}/space`)).status(),
    ).toBe(403);
    const newNotices = await get<NotificationPage>(
      applicant.request,
      '/me/notifications',
    );
    expect(
      newNotices.data.filter(
        (notice) =>
          notice.applicationId === reapplication.id &&
          notice.eventStatus === 'submitted',
      ),
    ).toHaveLength(1);
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

// 서버 로그아웃으로 실제 세션을 회수한 뒤, 화면에 남은 캐시가 인증 실패로 제거되는지 확인합니다.
test('세션 회수 후 401은 캐시된 팀 공간을 숨기고 재로그인을 안내한다', async ({
  browser,
  resources,
}, testInfo) => {
  const owner = await browser.newContext({
    ...testInfo.project.use,
    baseURL,
    ignoreHTTPSErrors: true,
  });
  try {
    const contest = await selectContest(owner.request, resources);
    await createAccount(owner.request, resources);
    const team = await createTeam(owner.request, contest, resources);
    const page = await owner.newPage();
    await page.goto(`/teams/${team.id}?view=space`);
    await expect(
      page.getByRole('region', { name: '확정된 팀원' }),
    ).toBeVisible();
    expect((await write(owner.request, 'POST', '/auth/logout')).status()).toBe(
      204,
    );
    const deniedSpace = await owner.request.get(
      `/api/v1/teams/${team.id}/space`,
    );
    expect(deniedSpace.status()).toBe(401);
    expect((await deniedSpace.json()).error.code).toBe('UNAUTHENTICATED');
    // 화면 새로고침 없이 기존 팀 공간의 조작을 사용해 인증 실패를 전달합니다.
    await page.getByRole('button', { name: '모집 종료', exact: true }).click();
    const failure = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/teams/${team.id}/recruitment/closure`) &&
        response.request().method() === 'PUT',
    );
    await page
      .getByRole('dialog')
      .getByRole('button', { name: '모집 종료하기', exact: true })
      .click();
    expect((await failure).status()).toBe(401);
    await expect(page.getByRole('region', { name: '확정된 팀원' })).toHaveCount(
      0,
    );
    await expect(
      page.getByRole('link', { name: '로그인하기', exact: true }),
    ).toBeVisible();
    expect(
      (
        await get<Data<{ recruitmentState: string }>>(
          owner.request,
          `/teams/${team.id}`,
        )
      ).data.recruitmentState,
    ).toBe('open');
    await captureLayout(page, testInfo, 'session-revoked-team-space');
  } finally {
    await owner.close();
  }
});

// 오류 응답만 브라우저에서 주입하고 재시도는 동일한 실제 API·DB로 복구합니다.
test('알림 503 조회 실패는 빈 목록과 구분하고 필터를 유지하며 실제 API로 복구한다', async ({
  browser,
  resources,
}, testInfo) => {
  const owner = await browser.newContext({
    ...testInfo.project.use,
    baseURL,
    ignoreHTTPSErrors: true,
  });
  const applicant = await browser.newContext({
    ...testInfo.project.use,
    baseURL,
    ignoreHTTPSErrors: true,
  });
  try {
    const contest = await selectContest(owner.request, resources);
    await createAccount(owner.request, resources);
    await createAccount(applicant.request, resources, true);
    const team = await createTeam(owner.request, contest, resources);
    const application = await submit(applicant.request, team.id, resources);
    const before = await get<NotificationPage>(
      owner.request,
      '/me/notifications',
    );
    expect(
      before.data.some((notice) => notice.applicationId === application.id),
    ).toBe(true);
    const page = await owner.newPage();
    let failing = true;
    await page.route('**/api/v1/me/notifications*', (route) =>
      failing &&
      route.request().method() === 'GET' &&
      !route.request().url().includes('unreadOnly=true')
        ? route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({
              error: { code: 'UNAVAILABLE', message: 'E2E 일시 조회 오류' },
              requestId: `e2e-${resources.runId}`,
            }),
          })
        : route.continue(),
    );
    await page.goto('/workspace');
    await page.getByRole('button', { name: /^알림/ }).click();
    const inbox = page.getByRole('dialog', { name: '알림', exact: true });
    await expect(inbox.getByRole('alert')).toContainText(
      '알림을 불러오지 못했어요',
    );
    await expect(
      inbox.getByText('아직 알림이 없어요', { exact: true }),
    ).toHaveCount(0);
    const unreadResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/me/notifications?') &&
        response.url().includes('unreadOnly=true') &&
        response.status() === 200,
    );
    await inbox.getByRole('button', { name: /읽지 않음/ }).click();
    expect(
      ((await (await unreadResponse).json()) as NotificationPage).unreadCount,
    ).toBe(before.unreadCount);
    await expect(inbox.getByRole('list', { name: '알림 목록' })).toBeVisible();
    await expect(inbox.getByRole('status')).toHaveText(
      `읽지 않은 알림 ${before.unreadCount}개`,
    );
    await expect(inbox.getByRole('alert')).toContainText(
      '알림을 불러오지 못했어요',
    );
    await captureLayout(page, testInfo, 'notifications-query-error');
    failing = false;
    const recovered = page.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/me/notifications?') &&
        !response.url().includes('unreadOnly=true') &&
        response.status() === 200,
    );
    await inbox.getByRole('button', { name: '다시 시도', exact: true }).click();
    const actual = (await (await recovered).json()) as NotificationPage;
    expect(
      actual.data.some((notice) => notice.applicationId === application.id),
    ).toBe(true);
    await expect(inbox.getByRole('alert')).toHaveCount(0);
    await expect(
      inbox.getByRole('button', { name: /읽지 않음/ }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(inbox.getByRole('list', { name: '알림 목록' })).toBeVisible();
    expect(
      await get<NotificationPage>(owner.request, '/me/notifications'),
    ).toEqual(before);
    await captureLayout(page, testInfo, 'notifications-query-recovered');
  } finally {
    await Promise.all([owner.close(), applicant.close()]);
  }
});
