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

    const reviewing = await changeReview(
      leader.request,
      application,
      'review-start',
    );
    expect(reviewing.status).toBe('reviewing');
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

    const rejected = await changeReview(leader.request, reviewing, 'rejection');
    expect(rejected.status).toBe('rejected');
    await applicantPage.reload();
    await expect(
      applicantPage.getByText('미선발', { exact: true }),
    ).toBeVisible();
    const ownerPage = await leader.newPage();
    await ownerPage.goto(`/applicants/${application.id}`);
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
    const cancellation = await write(
      applicant.request,
      'PUT',
      `/applications/${selected.id}/cancellation`,
      { expectedVersion: selected.version },
    );
    expect(cancellation.status()).toBe(200);
    expect((await cancellation.json()).data.membershipEnded).toBe(true);
    expect(
      (
        await get<Data<Application>>(
          applicant.request,
          `/applications/${discarded.id}`,
        )
      ).data,
    ).toEqual(discarded);
    const reapplication = await submit(applicant.request, teamB.id, resources);
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
