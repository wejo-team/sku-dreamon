// 기존 지원 이력·100건 초과 목록·세션 만료의 화면 경계를 검증합니다.
import { act, screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { TeamPage, WorkspacePage } from '@/features/workspace/WorkspacePages';
import { listTeamApplicants } from '@/features/applications/api';
import { setupUser } from '@/test/user';
import { queryKeys } from '@/lib/query-keys';
import { state } from '@/lib/api-mock/state';
import {
  demoIds,
  ME,
  renderWithApi,
  recordsWithMyProfile,
  settled,
  mockDb,
} from '@/test/render';

const teamUi = (
  <Routes>
    <Route path="/teams/:teamId" element={<TeamPage />} />
  </Routes>
);
describe('workspace boundary regressions', () => {
  it('shows a truthful empty state when every application has been decided', async () => {
    const db = recordsWithMyProfile({ isPublic: true });
    db.applications = db.applications.map((application) => ({
      ...application,
      status: 'rejected',
    }));
    const view = renderWithApi(teamUi, {
      path: `/teams/${demoIds.teams.greenwave}?view=applicants&page=99`,
      signedIn: true,
      db,
    });
    await settled(view.client);
    expect(
      screen.getByText('현재 지원 중인 지원자가 없어요.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('navigation', { name: '지원자 목록 페이지' }),
    ).not.toBeInTheDocument();
    const history = await listTeamApplicants(demoIds.teams.greenwave);
    expect(history.data.length).toBeGreaterThan(0);
  });

  it('pages only ongoing applicants and returns to a valid page after a decision', async () => {
    const db = recordsWithMyProfile({ isPublic: true });
    const original = db.applications.find(
      (item) => item.teamId === demoIds.teams.greenwave,
    )!;
    const profile = db.profiles.find(
      (item) => item.accountId === original.applicantAccountId,
    )!;
    db.applications = db.applications.filter(
      (item) => item.teamId !== demoIds.teams.greenwave,
    );
    const statuses = [
      'submitted',
      'reviewing',
      'submitted',
      'reviewing',
      'submitted',
      'reviewing',
      'submitted',
      'selected',
      'rejected',
      'canceled',
      'discarded',
    ] as const;
    statuses.forEach((status, index) => {
      const accountId = crypto.randomUUID();
      db.profiles.push({
        ...profile,
        accountId,
        realName: `지원상태후보${index}`,
      });
      db.applications.push({
        ...original,
        id: crypto.randomUUID(),
        applicantAccountId: accountId,
        status,
        discardReason: status === 'discarded' ? 'selected_elsewhere' : null,
        submittedAt: new Date(Date.UTC(2026, 9, 1, 0, index)).toISOString(),
      });
    });
    const view = renderWithApi(teamUi, {
      path: `/teams/${demoIds.teams.greenwave}?view=applicants&page=2`,
      signedIn: true,
      db,
    });
    await settled(view.client);
    expect(
      screen.getAllByRole('link', { name: /지원상태후보\d+ 지원서 검토/ }),
    ).toHaveLength(1);
    expect(
      screen.getByRole('link', { name: /지원상태후보0 지원서 검토/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: '지원자 목록 페이지' }),
    ).toHaveTextContent('전체 2페이지 중 2페이지');
    const oldest = mockDb().applications.find(
      (item) =>
        item.teamId === demoIds.teams.greenwave &&
        item.submittedAt === '2026-10-01T00:00:00.000Z',
    )!;
    oldest.status = 'rejected';
    await act(async () => {
      await view.client.invalidateQueries({
        queryKey: ['applications', 'applicants', demoIds.teams.greenwave],
      });
    });
    await settled(view.client);
    expect(
      screen.queryByRole('link', { name: /지원상태후보0 지원서 검토/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByRole('link', { name: /지원상태후보\d+ 지원서 검토/ }),
    ).toHaveLength(6);
    expect(
      screen.queryByRole('navigation', { name: '지원자 목록 페이지' }),
    ).not.toBeInTheDocument();
    for (const index of [7, 8, 9, 10]) {
      expect(
        screen.queryByRole('link', {
          name: new RegExp(`지원상태후보${index} 지원서 검토`),
        }),
      ).not.toBeInTheDocument();
    }
  });

  it('permits a new application after a discarded application and no current membership', async () => {
    const db = recordsWithMyProfile({ isPublic: true });
    const original = db.applications[0]!;
    db.applications.push({
      ...original,
      id: crypto.randomUUID(),
      teamId: demoIds.teams.makers,
      contestId: demoIds.contests.campus,
      applicantAccountId: ME,
      status: 'discarded',
      discardReason: 'selected_elsewhere',
      discardedByApplicationId: original.id,
    });
    const view = renderWithApi(teamUi, {
      path: `/teams/${demoIds.teams.makers}`,
      signedIn: true,
      db,
    });
    await settled(view.client);
    expect(
      screen.getByRole('button', { name: '이 팀에 지원하기' }),
    ).toBeInTheDocument();
    const user = setupUser();
    await user.click(screen.getByRole('radio', { name: '디자인' }));
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    await settled(view.client);
    expect(screen.getByText('지원이 완료됐어요')).toBeInTheDocument();
    expect(
      mockDb()
        .applications.filter(
          (item) =>
            item.teamId === demoIds.teams.makers &&
            item.applicantAccountId === ME,
        )
        .map((item) => item.status)
        .sort(),
    ).toEqual(['discarded', 'submitted']);
  });

  it('provides a path to the 101st applicant instead of hiding it permanently', async () => {
    const db = recordsWithMyProfile({ isPublic: true });
    const original = db.applications.find(
      (item) => item.teamId === demoIds.teams.greenwave,
    )!;
    const profile = db.profiles.find(
      (item) => item.accountId === original.applicantAccountId,
    )!;
    db.applications = db.applications.filter(
      (item) => item.teamId !== demoIds.teams.greenwave,
    );
    for (let index = 0; index < 101; index++) {
      const accountId = crypto.randomUUID();
      db.profiles.push({ ...profile, accountId, realName: `검토후보${index}` });
      db.applications.push({
        ...original,
        id: crypto.randomUUID(),
        applicantAccountId: accountId,
        submittedAt: new Date(Date.UTC(2026, 9, 1, 0, index)).toISOString(),
      });
    }
    const view = renderWithApi(teamUi, {
      path: `/teams/${demoIds.teams.greenwave}?view=applicants`,
      signedIn: true,
      db,
    });
    await settled(view.client);
    const lastPage = await listTeamApplicants(demoIds.teams.greenwave, {
      page: 2,
      pageSize: 100,
    });
    expect(lastPage.pagination.total).toBe(101);
    expect(lastPage.data).toHaveLength(1);
    expect(lastPage.data[0]!.profile.realName).toBe('검토후보0');
    expect(
      screen.getAllByRole('link', { name: /검토후보\d+ 지원서 검토/ }),
    ).toHaveLength(6);
    const user = setupUser();
    for (let page = 1; page < 17; page++) {
      await user.click(
        within(
          screen.getByRole('navigation', { name: '지원자 목록 페이지' }),
        ).getByRole('link', { name: '다음 페이지' }),
      );
      await settled(view.client);
    }
    expect(
      screen.getByRole('link', { name: '검토후보0 지원서 검토, 시연 계정' }),
    ).toBeInTheDocument();
  });

  it('hides cached private team space and requests login after an explicit 401', async () => {
    const view = renderWithApi(teamUi, {
      path: `/teams/${demoIds.teams.greenwave}?view=space`,
      signedIn: true,
      db: recordsWithMyProfile({ isPublic: true }),
    });
    await settled(view.client);
    expect(
      screen.getByRole('region', { name: '확정된 팀원' }),
    ).toBeInTheDocument();
    state.sessionAccountId = null;
    await act(async () => {
      await view.client.invalidateQueries({
        queryKey: queryKeys.teamSpace(demoIds.teams.greenwave),
      });
    });
    await settled(view.client);

    expect(
      screen.queryByRole('region', { name: '확정된 팀원' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '로그인하기' }),
    ).toBeInTheDocument();
    expect(view.client.getQueryData(queryKeys.me)).toBeNull();
  });
});

it('finds an existing application after 100 newer records on other teams', async () => {
  const db = recordsWithMyProfile({ isPublic: true });
  const original = db.applications[0]!;
  db.applications = [
    {
      ...original,
      id: crypto.randomUUID(),
      teamId: demoIds.teams.makers,
      contestId: demoIds.contests.campus,
      status: 'submitted',
      submittedAt: '2026-09-01T00:00:00Z',
    },
    ...Array.from({ length: 100 }, () => ({
      ...original,
      id: crypto.randomUUID(),
      status: 'canceled' as const,
    })),
  ];
  const view = renderWithApi(teamUi, {
    path: `/teams/${demoIds.teams.makers}`,
    signedIn: true,
    db,
  });
  await settled(view.client);
  expect(
    screen.getByText(/이미 .* 역할로 지원한 팀이에요/),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: '이 팀에 지원하기' }),
  ).not.toBeInTheDocument();
  view.unmount();
  const workspace = renderWithApi(<WorkspacePage />, {
    path: '/workspace?view=applications&page=17',
    signedIn: true,
    db,
  });
  await settled(workspace.client);
  expect(
    screen.getByRole('navigation', { name: '내 지원 페이지' }),
  ).toHaveTextContent('17페이지');
  expect(screen.getByText('캠퍼스 메이커스')).toBeInTheDocument();
});

it('shows membership beyond the first 100 teams and pages through my teams', async () => {
  const db = recordsWithMyProfile({ isPublic: true });
  const team = db.teams.find((item) => item.id === demoIds.teams.greenwave)!;
  const contest = db.contests.find((item) => item.id === team.contestId)!;
  const membership = db.memberships.find(
    (item) => item.teamId === team.id && item.accountId === ME,
  )!;
  team.createdAt = '2026-09-01T00:00:00Z';
  membership.joinedAt = '2026-09-01T00:00:00Z';
  for (let index = 0; index < 100; index++) {
    const contestId = crypto.randomUUID();
    const teamId = crypto.randomUUID();
    db.contests.push({ ...contest, id: contestId });
    db.teams.push({
      ...team,
      id: teamId,
      contestId,
      name: `추가팀${index}`,
      createdAt: new Date(Date.UTC(2026, 9, 1, 0, index)).toISOString(),
    });
    db.memberships.push({
      ...membership,
      joinedAt: new Date(Date.UTC(2026, 9, 1, 0, index)).toISOString(),
      teamId,
      membershipId: crypto.randomUUID(),
    });
  }
  const view = renderWithApi(teamUi, {
    path: `/teams/${team.id}`,
    signedIn: true,
    db,
  });
  await settled(view.client);
  expect(screen.getByText('이미 함께하고 있는 팀이에요.')).toBeInTheDocument();
  view.unmount();
  const workspace = renderWithApi(<WorkspacePage />, {
    path: '/workspace?page=17',
    signedIn: true,
    db,
  });
  await settled(workspace.client);
  expect(
    screen.getByRole('navigation', { name: '내 팀 페이지' }),
  ).toHaveTextContent('17페이지');
  expect(
    screen.getByRole('link', { name: `${team.name} 팀 공간으로, 시연 팀` }),
  ).toBeInTheDocument();
});

it.each([403, 404, 503])(
  'hides cached team space after %s while preserving the signed-in session',
  async (status) => {
    const view = renderWithApi(teamUi, {
      path: `/teams/${demoIds.teams.greenwave}?view=space`,
      signedIn: true,
    });
    await settled(view.client);
    expect(
      screen.getByRole('region', { name: '확정된 팀원' }),
    ).toBeInTheDocument();
    const fetch = globalThis.fetch;
    vi.stubGlobal('fetch', (input: string, init?: RequestInit) =>
      String(input).includes('/space')
        ? Promise.resolve(
            Response.json(
              {
                error: { code: 'TEST_FAILURE', message: '오류' },
                requestId: 'test',
              },
              { status },
            ),
          )
        : fetch(input, init),
    );
    await act(async () => {
      await view.client.invalidateQueries({
        queryKey: queryKeys.teamSpace(demoIds.teams.greenwave),
      });
    });
    await settled(view.client);
    expect(
      screen.queryByRole('region', { name: '확정된 팀원' }),
    ).not.toBeInTheDocument();
    expect(view.client.getQueryData(queryKeys.me)).not.toBeNull();
    if (status === 503)
      expect(
        screen.getByRole('button', { name: '다시 시도' }),
      ).toBeInTheDocument();
    else
      expect(
        screen.getByText('현재 팀원만 팀 공간에 들어갈 수 있어요'),
      ).toBeInTheDocument();
  },
);
