import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useQuery } from '@tanstack/react-query';
import { Route, Routes, useLocation } from 'react-router';
import { describe, expect, it } from 'vitest';
import {
  ApplicantPage,
  TeamPage,
  WorkspacePage,
} from '@/features/workspace/WorkspacePages';
import { CreateTeamPage } from '@/features/teams/CreateTeamPage';
import {
  myProfileQueryOptions,
  useSaveVisibility,
} from '@/features/profiles/queries';
import { lifecycleReferenceDatabase } from '@/features/demo/lifecycle-fixtures';
import {
  createDemoRecords,
  fixtureAcademicUnits,
  type DemoDatabase,
} from '@/features/demo/fixtures';
import {
  demoIds,
  ME,
  recordsWithMyProfile,
  renderWithApi,
  sentRequests,
  settled,
  withProfile,
  type ApiRenderOptions,
} from '@/test/render';
import { TestSessionButton } from '@/test/providers';

const seed = createDemoRecords();
const seoyeonProfile = seed.profiles.find(
  (item) => item.accountId === demoIds.accounts.seoyeon,
)!;
const seoyeonApplication = seed.applications.find(
  (item) => item.id === demoIds.applications.seoyeon,
)!;
// 본인 프로필을 공개한 목업 저장소
const publicRecords = () => recordsWithMyProfile({ isPublic: true });
const lifecycleRecords = () =>
  withProfile(lifecycleReferenceDatabase(), ME, { isPublic: true });
// 그린웨이브 팀 레코드만 바꾼 저장소(현재 팀원은 2명)
const greenwaveWith = (
  patch: Partial<DemoDatabase['teams'][number]>,
): DemoDatabase => {
  const db = publicRecords();
  return {
    ...db,
    teams: db.teams.map((team) =>
      team.id === demoIds.teams.greenwave ? { ...team, ...patch } : team,
    ),
  };
};
// 서버 충돌(409)로 실패시킬 요청
const failApply = ({ method, path }: { method: string; path: string }) =>
  method === 'POST' && path.endsWith('/applications');
const failReopen = ({ method, path }: { method: string; path: string }) =>
  method === 'PUT' && path.endsWith('/recruitment/reopening');

// 테스트 조작: 로그인·로그아웃(목업 API), 현재 프로필 공개 전환(PUT /me/profile/visibility)
function TestControls() {
  const profile = useQuery(myProfileQueryOptions).data;
  const saveVisibility = useSaveVisibility();
  return (
    <>
      <TestSessionButton />
      <button
        onClick={() =>
          profile &&
          saveVisibility.mutate({
            expectedVersion: profile.version,
            isPublic: true,
          })
        }
      >
        테스트 공개
      </button>
    </>
  );
}
function CurrentLocation() {
  const { pathname, search } = useLocation();
  return (
    <output aria-label="현재 경로">
      {pathname}
      {search}
    </output>
  );
}
async function renderPage(path: string, options: ApiRenderOptions = {}) {
  const view = renderWithApi(
    <>
      <TestControls />
      <CurrentLocation />
      <Routes>
        <Route path="/explore" element={<p>팀 탐색 목록</p>} />
        <Route path="/teams/new" element={<CreateTeamPage />} />
        <Route path="/teams/:teamId" element={<TeamPage />} />
        <Route path="/workspace" element={<WorkspacePage />} />
        <Route path="/applicants/:applicantId" element={<ApplicantPage />} />
      </Routes>
    </>,
    { path, ...options },
  );
  await screen.findByLabelText('현재 경로');
  await settled(view.client);
  const user = userEvent.setup();
  // 사용자 조작 뒤 다음 요청이 끝날 때까지 기다립니다.
  const step = async (action: () => Promise<void>) => {
    await action();
    await settled(view.client);
  };
  return { ...view, user, step };
}
// 화면 조작으로 로그인(POST /auth/login)
const signIn = (step: (action: () => Promise<void>) => Promise<void>) =>
  step(() =>
    userEvent.click(screen.getByRole('button', { name: '테스트 로그인' })),
  );

describe('team application', () => {
  it('accepts an unadvertised role and links the new application to its result', async () => {
    const { user, step } = await renderPage(`/teams/${demoIds.teams.makers}`);
    await signIn(step);
    expect(
      screen.getByText('프로필을 공개한 뒤 지원할 수 있어요'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '이 팀에 지원하기' }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '프로필 공개하기' }));
    const privacyDialog = within(screen.getByRole('dialog'));
    expect(
      privacyDialog.getByText(/공개 전환만으로 지원이 접수되지는 않아요/),
    ).toBeInTheDocument();
    await user.click(privacyDialog.getByRole('button', { name: '취소' }));
    expect(
      screen.getByText('프로필을 공개한 뒤 지원할 수 있어요'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '프로필 공개하기' }));
    await step(() =>
      user.click(
        within(screen.getByRole('dialog')).getByRole('button', {
          name: '공개로 전환',
        }),
      ),
    );
    expect(screen.queryByText('지원이 완료됐어요')).not.toBeInTheDocument();
    expect(
      await screen.findByText(/AI 검토에 최신 프로필을 사용할 수 있어요/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    expect(
      await screen.findByText('지원할 역할을 선택해 주세요.'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: '마케팅' }));
    await user.type(
      screen.getByLabelText(/팀에 전할 말/),
      '사용자 인터뷰를 함께하고 싶어요.',
    );
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    expect(await screen.findByText('지원이 완료됐어요')).toBeInTheDocument();
    await step(() =>
      user.click(screen.getByRole('link', { name: '내 지원 확인하기' })),
    );
    const applications = within(
      screen.getByRole('region', { name: '내 지원' }),
    );
    expect(applications.getByText('캠퍼스 메이커스')).toBeInTheDocument();
    expect(applications.getByText('마케팅 지원')).toBeInTheDocument();
    expect(applications.getByText('지원 완료')).toBeInTheDocument();
    const submitted =
      applications.getByText('사용자 인터뷰를 함께하고 싶어요.');
    await user.click(
      within(submitted.closest('details')!).getByText('내가 전한 말'),
    );
    expect(submitted).toBeVisible();
  });
  it('gates missing required profile fields and preserves the target team', async () => {
    await renderPage(`/teams/${demoIds.teams.makers}`, {
      signedIn: true,
      db: recordsWithMyProfile({ isPublic: true, fieldCodes: [] }),
    });
    expect(
      screen.getByText('지원 전에 프로필을 완성해 주세요'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '프로필 보완하기' }),
    ).toHaveAttribute(
      'href',
      `/profile?edit=details&returnTo=${encodeURIComponent(`/teams/${demoIds.teams.makers}`)}`,
    );
    expect(
      screen.queryByRole('button', { name: '이 팀에 지원하기' }),
    ).not.toBeInTheDocument();
  });
  it('preserves written text after failure and rejects a logged-out delayed submission', async () => {
    const first = await renderPage(`/teams/${demoIds.teams.makers}`, {
      signedIn: true,
      db: publicRecords(),
      fail: failApply,
    });
    await first.user.click(screen.getByRole('radio', { name: '디자인' }));
    await first.user.type(
      screen.getByLabelText(/팀에 전할 말/),
      '화면 설계를 맡고 싶어요.',
    );
    await first.user.click(
      screen.getByRole('button', { name: '이 팀에 지원하기' }),
    );
    expect(
      await screen.findByText(/지원을 완료하지 못했어요/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/팀에 전할 말/)).toHaveValue(
      '화면 설계를 맡고 싶어요.',
    );
    first.unmount();
    const { user, step } = await renderPage(`/teams/${demoIds.teams.makers}`);
    await signIn(step);
    await step(() =>
      user.click(screen.getByRole('button', { name: '테스트 공개' })),
    );
    await user.click(await screen.findByRole('radio', { name: '기획' }));
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    await user.click(screen.getByRole('button', { name: '테스트 로그아웃' }));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 400));
    });
    expect(
      await screen.findByRole('link', { name: '로그인하고 지원하기' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('지원이 완료됐어요')).not.toBeInTheDocument();
  });
  it('preserves an over-limit application message and accepts the 1,000-codepoint boundary', async () => {
    const { user } = await renderPage(`/teams/${demoIds.teams.makers}`, {
      signedIn: true,
      db: publicRecords(),
      fail: failApply,
    });
    await user.click(screen.getByRole('radio', { name: '디자인' }));
    const field = screen.getByLabelText(/팀에 전할 말/);
    await user.click(field);
    await user.paste('🎨'.repeat(1001));
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    expect(
      await screen.findByText('팀에 전할 말은 1,000자까지 입력할 수 있어요.'),
    ).toBeInTheDocument();
    expect(field).toHaveValue('🎨'.repeat(1001));
    const applyRequests = () =>
      sentRequests.filter((request) => failApply(request));
    expect(applyRequests()).toHaveLength(0);
    await user.clear(field);
    await user.paste('🎨'.repeat(1000));
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    await screen.findByText(/지원을 완료하지 못했어요/);
    // docs/api/applications.md#application-create: POST /teams/{teamId}/applications 본문
    expect(applyRequests()).toEqual([
      {
        method: 'POST',
        path: `/teams/${demoIds.teams.makers}/applications`,
        body: {
          requestId: expect.any(String),
          roleCode: 'design',
          message: '🎨'.repeat(1000),
        },
      },
    ]);
  });
  it('keeps public recruitment separate from the private team space', async () => {
    const { user, step } = await renderPage(
      `/teams/${demoIds.teams.greenwave}`,
      { signedIn: true, db: publicRecords() },
    );
    expect(
      screen.getByRole('heading', { name: '모집 정보' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '확정된 팀원' }),
    ).not.toBeInTheDocument();
    await step(() =>
      user.click(screen.getByRole('link', { name: '팀 공간으로' })),
    );
    expect(
      screen.getByRole('heading', { name: '확정된 팀원' }),
    ).toBeInTheDocument();
    expect(screen.getByText('내 역할').parentElement).toHaveTextContent('팀장');
  });
  it('preserves filtered return destinations and rejects external ones', async () => {
    const from = '/explore?tab=teams&role=design&q=캠퍼스';
    const view = await renderPage(
      `/teams/${demoIds.teams.makers}?from=${encodeURIComponent(from)}`,
    );
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute(
      'href',
      from,
    );
    view.unmount();
    await renderPage(
      `/teams/${demoIds.teams.makers}?from=${encodeURIComponent('https://example.com')}`,
    );
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute(
      'href',
      '/explore?tab=teams',
    );
  });
});

describe('workspace membership and access', () => {
  it('shows leader and member teams but hides activity before login', async () => {
    const { step } = await renderPage('/workspace');
    expect(screen.queryByText('그린웨이브')).not.toBeInTheDocument();
    await signIn(step);
    expect(
      screen.getByRole('heading', { name: '그린웨이브' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: '로컬 크루' }),
    ).toBeInTheDocument();
  });
  it('shows the first-team prompt when the account belongs to no team', async () => {
    const records = createDemoRecords();
    await renderPage('/workspace', {
      signedIn: true,
      db: {
        ...records,
        memberships: records.memberships.filter(
          (item) => item.accountId !== ME,
        ),
      },
    });
    expect(screen.getByText('함께할 첫 팀을 찾아보세요')).toBeInTheDocument();
  });
  it('allows members to view the team but does not grant management rights', async () => {
    const view = await renderPage(
      `/teams/${demoIds.teams.localcrew}?view=space`,
      { signedIn: true },
    );
    expect(
      screen.getByRole('heading', { name: '확정된 팀원' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '지원자 관리' }),
    ).not.toBeInTheDocument();
    view.unmount();
    await renderPage(`/teams/${demoIds.teams.localcrew}?view=applicants`, {
      signedIn: true,
    });
    expect(
      screen.getByText('팀장만 지원서를 볼 수 있어요'),
    ).toBeInTheDocument();
  });
  it('revokes team-space access after a selected member cancels', async () => {
    const { user, step } = await renderPage('/workspace?view=applications');
    await signIn(step);
    await user.click(screen.getByRole('button', { name: '지원 취소' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText(/팀 공간에 접근할 수 없게/)).toBeInTheDocument();
    await step(() =>
      user.click(dialog.getByRole('button', { name: '지원 취소하기' })),
    );
    expect(
      screen.getByText(
        '지원이 취소됐어요. 현재 모집 조건이 맞으면 다시 지원할 수 있어요.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '팀 공간으로' }),
    ).not.toBeInTheDocument();
    await step(() =>
      user.click(screen.getByRole('link', { name: '내 팀으로' })),
    );
    expect(
      screen.queryByRole('heading', { name: '로컬 크루' }),
    ).not.toBeInTheDocument();
  });
  it('rejects direct private-space access for a nonmember', async () => {
    await renderPage(`/teams/${demoIds.teams.makers}?view=space`, {
      signedIn: true,
    });
    expect(
      screen.getByText('현재 팀원만 팀 공간에 들어갈 수 있어요'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '확정된 팀원' }),
    ).not.toBeInTheDocument();
  });
  it('requires confirmation to close recruitment and keeps the current team', async () => {
    const { user, step } = await renderPage(
      `/teams/${demoIds.teams.greenwave}?view=space`,
    );
    await signIn(step);
    await user.click(screen.getByRole('button', { name: '모집 종료' }));
    await step(() =>
      user.click(
        within(screen.getByRole('dialog')).getByRole('button', {
          name: '모집 종료하기',
        }),
      ),
    );
    expect(screen.getByText('모집 마감')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: '확정된 팀원' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '모집 종료' }),
    ).not.toBeInTheDocument();
  });
});

describe('applicant review', () => {
  it('confirms selection in a drawer and immediately adds the selected member', async () => {
    const { user, step } = await renderPage(
      `/applicants/${demoIds.applications.seoyeon}`,
    );
    await signIn(step);
    const profile = within(screen.getByRole('region', { name: '김서연' }));
    expect(profile.getByText('경험')).toBeInTheDocument();
    expect(
      profile.getByText(seoyeonProfile.experienceBody!),
    ).toBeInTheDocument();
    expect(profile.getByText(seoyeonProfile.introduction!)).toBeInTheDocument();
    expect(
      profile.getByRole('link', { name: /김서연의 프로젝트\s*\(새 창\)/ }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: '이 지원자 선발하기' }),
    );
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText(/즉시 팀원이 확정/)).toBeInTheDocument();
    await step(() =>
      user.click(dialog.getByRole('button', { name: '선발하고 팀원 확정' })),
    );
    expect(
      screen.getByText('김서연 님이 팀원으로 확정됐어요'),
    ).toBeInTheDocument();
    await step(() =>
      user.click(screen.getByRole('link', { name: '팀 공간으로' })),
    );
    expect(screen.getByText('확정').parentElement).toHaveTextContent('3 / 4명');
    expect(
      within(screen.getByRole('region', { name: '확정된 팀원' })).getByText(
        '김서연',
      ),
    ).toBeInTheDocument();
  });
  it('shows a private applicant’s full registered profile to the applied team leader', async () => {
    const units = fixtureAcademicUnits();
    const department = units.find((unit) => unit.name === '자유전공학부')!;
    const major = units.find(
      (unit) =>
        unit.parentId === department.id && unit.name === 'AI소프트웨어전공',
    )!;
    const db = withProfile(publicRecords(), demoIds.accounts.seoyeon, {
      introduction: '지원자의 자기소개',
      experienceState: 'provided',
      experienceBody: '지원자의 경험',
      academicStatusCode: 'enrolled',
      gradeCode: 'year_3',
      academicUnitId: major.id,
      skillCodes: ['data_analysis'],
      fieldCodes: ['education'],
      weeklyAvailabilityCode: 'from_5_to_10',
      isPublic: false,
      portfolio: {
        url: 'https://example.com/secret',
        title: '지원자의 포트폴리오',
      },
    });
    await renderPage(`/applicants/${demoIds.applications.seoyeon}`, {
      signedIn: true,
      db,
    });
    for (const value of [
      '지원자의 자기소개',
      '지원자의 경험',
      '재학',
      '3학년',
      '미래융합대학',
      '자유전공학부',
      'AI소프트웨어전공',
      '데이터분석',
      '교육',
      '5~10시간 미만',
    ]) {
      expect(screen.getByText(value)).toBeInTheDocument();
    }
    expect(
      screen.getByRole('link', { name: /지원자의 포트폴리오\s*\(새 창\)/ }),
    ).toHaveAttribute('href', 'https://example.com/secret');
    expect(
      screen.getByText(/공개 설정과 관계없이 등록한 전체 프로필/),
    ).toBeInTheDocument();
    expect(screen.getByText('교내 미인증')).toBeInTheDocument();
  });
  it.each(['leader_closed', 'capacity_reached'] as const)(
    'allows AI review for existing applicants while recruitment is closed by %s',
    async (closedReason) => {
      const { user } = await renderPage(
        `/applicants/${demoIds.applications.seoyeon}`,
        {
          signedIn: true,
          db: greenwaveWith({
            recruitmentState: 'closed',
            closedReason,
            capacity: '2',
          }),
        },
      );
      expect(
        screen.queryByRole('button', { name: '이 지원자 선발하기' }),
      ).not.toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
      expect(
        await within(
          screen.getByRole('region', { name: 'AI 검토 도움' }),
        ).findByRole('status'),
      ).toHaveTextContent(seoyeonApplication.message!);
      expect(
        screen.getByRole('button', { name: '다시 검토하기' }),
      ).toBeEnabled();
    },
  );
  it('does not expose applications to a nonleader', async () => {
    await renderPage(`/applicants/${demoIds.applications.seoyeon}`, {
      signedIn: true,
      db: greenwaveWith({ ownerAccountId: demoIds.accounts.doyun }),
    });
    expect(screen.getByText('지원서를 확인할 수 없어요')).toBeInTheDocument();
    expect(screen.queryByText('김서연')).not.toBeInTheDocument();
    expect(
      screen.queryByText(seoyeonProfile.experienceBody!),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /김서연의 프로젝트/ }),
    ).not.toBeInTheDocument();
  });
  it('does not expose applicant details before login', async () => {
    await renderPage(`/applicants/${demoIds.applications.seoyeon}`);
    expect(screen.getByText('로그인하고 이어가세요')).toBeInTheDocument();
    expect(screen.queryByText('김서연')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /김서연의 프로젝트/ }),
    ).not.toBeInTheDocument();
  });
});

describe('team creation', () => {
  it('shows capacity and deadline constraints in the official creation flow', async () => {
    const { user } = await renderPage(
      `/teams/new?contestId=${demoIds.contests.campus}`,
      { signedIn: true, db: publicRecords() },
    );
    expect(screen.getByLabelText('팀장 포함 총 정원')).toHaveAttribute(
      'min',
      '2',
    );
    expect(screen.getByLabelText('팀장 포함 총 정원')).toHaveAttribute(
      'max',
      '5',
    );
    expect(screen.getByLabelText('팀 모집 마감')).toHaveAttribute(
      'max',
      '2026-11-08',
    );
    await user.type(screen.getByLabelText('팀장 포함 총 정원'), '3');
    expect(screen.getByText(/다른 역할/)).toBeInTheDocument();
  });
});

describe('recruitment reopening and discarded history', () => {
  it('requires confirmation to reopen, preserves cancellation and announces success', async () => {
    const { user, step } = await renderPage(
      `/teams/${demoIds.teams.greenwave}?view=space`,
    );
    await signIn(step);
    await user.click(screen.getByRole('button', { name: '모집 종료' }));
    await step(() =>
      user.click(
        within(screen.getByRole('dialog')).getByRole('button', {
          name: '모집 종료하기',
        }),
      ),
    );
    expect(screen.getByText('모집 마감')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '다시 모집하기' }));
    expect(
      within(screen.getByRole('dialog')).getByText(
        /폐기된 지원은 복원되지 않아요/,
      ),
    ).toBeInTheDocument();
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '돌아가기',
      }),
    );
    expect(screen.getByText('모집 마감')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '다시 모집하기' }));
    await step(() =>
      user.click(
        within(screen.getByRole('dialog')).getByRole('button', {
          name: '모집 중으로 변경',
        }),
      ),
    );
    expect(screen.getByText('모집 중')).toBeInTheDocument();
    expect(
      within(screen.getByRole('region', { name: '모집 관리' })).getByRole(
        'status',
      ),
    ).toHaveTextContent('모집을 다시 시작했어요');
    expect(
      screen.queryByRole('button', { name: '다시 모집하기' }),
    ).not.toBeInTheDocument();
  });

  it('shows why a full team cannot reopen and gives no management action to a member', async () => {
    const db = greenwaveWith({
      recruitmentState: 'closed',
      closedReason: 'leader_closed',
      capacity: '2',
    });
    const view = await renderPage(
      `/teams/${demoIds.teams.greenwave}?view=space`,
      { signedIn: true, db },
    );
    expect(
      screen.getByRole('button', { name: '다시 모집하기' }),
    ).toBeDisabled();
    expect(
      screen.getByText('팀 정원이 모두 차서 다시 모집할 수 없어요.'),
    ).toBeInTheDocument();
    view.unmount();
    await renderPage(`/teams/${demoIds.teams.localcrew}?view=space`, {
      signedIn: true,
    });
    expect(
      screen.queryByRole('button', { name: '다시 모집하기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '모집 종료' }),
    ).not.toBeInTheDocument();
  });

  it('retains the closed state when a reopen request fails', async () => {
    const { user, step } = await renderPage(
      `/teams/${demoIds.teams.greenwave}?view=applicants`,
      { signedIn: true, db: lifecycleRecords(), fail: failReopen },
    );
    await user.click(screen.getByRole('button', { name: '다시 모집하기' }));
    await step(() =>
      user.click(
        within(screen.getByRole('dialog')).getByRole('button', {
          name: '모집 중으로 변경',
        }),
      ),
    );
    // docs/api/teams.md#transitions: PUT …/recruitment/reopening 한 번, 실패 후 자동 재전송 없음
    expect(sentRequests.filter(failReopen)).toEqual([
      {
        method: 'PUT',
        path: `/teams/${demoIds.teams.greenwave}/recruitment/reopening`,
        body: { expectedVersion: '2' },
      },
    ]);
    await waitFor(() =>
      expect(
        within(screen.getByRole('dialog')).getByRole('alert'),
      ).toHaveTextContent('처리하지 못했어요'),
    );
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '돌아가기',
      }),
    );
    expect(screen.getByText('모집 마감')).toBeInTheDocument();
  });

  it('shows discarded history and reason in my applications without cancellation or team-space access', async () => {
    await renderPage('/workspace?view=applications', {
      signedIn: true,
      db: lifecycleRecords(),
    });
    const discarded = screen.getByText('로컬 스튜디오').closest('li')!;
    expect(within(discarded).getByText('폐기')).toBeInTheDocument();
    expect(
      within(discarded).getByText(/같은 공모전의 다른 팀에서 선발/),
    ).toBeInTheDocument();
    expect(
      within(discarded).queryByRole('button', { name: '지원 취소' }),
    ).not.toBeInTheDocument();
    expect(
      within(discarded).queryByRole('link', { name: '팀 공간으로' }),
    ).not.toBeInTheDocument();
  });

  it('keeps factual AI review for discarded applicants while excluding waiting counts and selection', async () => {
    const view = await renderPage(
      `/teams/${demoIds.teams.greenwave}?view=applicants`,
      { signedIn: true, db: lifecycleRecords() },
    );
    expect(screen.getByText('검토 대기 1명')).toBeInTheDocument();
    expect(
      screen.getByText('같은 공모전의 다른 팀에서 선발됨'),
    ).toBeInTheDocument();
    view.unmount();
    const { user } = await renderPage(
      `/applicants/${demoIds.applications.seoyeon}`,
      { signedIn: true, db: lifecycleRecords() },
    );
    expect(screen.getByText('폐기')).toBeInTheDocument();
    expect(
      screen.getByText(seoyeonProfile.experienceBody!),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '이 지원자 선발하기' }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(
      await within(
        screen.getByRole('region', { name: 'AI 검토 도움' }),
      ).findByRole('status'),
    ).toHaveTextContent(seoyeonApplication.message!);
    expect(
      screen.getByText(/폐기된 지원은 새 선발 후보 추천에서 제외/),
    ).toBeInTheDocument();
  });
});
