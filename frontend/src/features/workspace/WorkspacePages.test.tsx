import { act, screen, waitFor, within } from '@testing-library/react';
import { fill, setupUser } from '@/test/user';
import { useQuery } from '@tanstack/react-query';
import { Route, Routes, useLocation } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import type { ApplicationStatus } from '@/features/applications/api';
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
import { useSignup } from '@/features/auth/queries';
import {
  createDemoRecords,
  fixtureAcademicUnits,
  type DemoDatabase,
} from '@/features/demo/fixtures';
import {
  demoIds,
  ME,
  mockDb,
  recordsWithMyProfile,
  renderWithApi,
  sentRequests,
  settled,
  withProfile,
  type ApiRenderOptions,
} from '@/test/render';
import { TestSessionButton } from '@/test/providers';

// 기존 시나리오는 데모 모드를 검증하며 실제 AI는 TargetAiPanel.test.tsx에서 검증합니다.
vi.mock('@/features/teams/ApplicantReview', async () => ({
  ApplicantReview: (await import('@/features/teams/MockApplicantReview'))
    .MockApplicantReview,
}));

const seed = createDemoRecords();
const seoyeonProfile = seed.profiles.find(
  (item) => item.accountId === demoIds.accounts.seoyeon,
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
  const signup = useSignup();
  return (
    <>
      <TestSessionButton />
      {/* 다른 계정으로 전환: 가입(POST /accounts)은 성공하면 바로 새 계정으로 로그인됩니다. */}
      <button
        onClick={() =>
          signup.mutate({
            loginId: 'otheraccount',
            password: 'OtherAccountPassword1!',
          })
        }
      >
        다른 계정으로 전환
      </button>
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
  const user = setupUser();
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
    setupUser().click(screen.getByRole('button', { name: '테스트 로그인' })),
  );

describe('team application', () => {
  it('labels an unverified collection link as its source on the team overview', async () => {
    const db = createDemoRecords();
    const contest = db.contests.find(
      (item) => item.id === demoIds.contests.campus,
    )!;
    contest.verifiedAt = null;
    contest.officialUrl = null;
    contest.sourceUrl = 'https://collection.example.com/notice/123';
    await renderPage(`/teams/${demoIds.teams.makers}`, { db });
    expect(
      screen.getByRole('link', { name: '수집 출처 보기' }),
    ).toHaveAttribute('href', contest.sourceUrl);
    expect(
      screen.queryByRole('link', { name: '공식 원문 보기' }),
    ).not.toBeInTheDocument();
  });

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
    await fill(
      user,
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
      screen.queryByRole('heading', { name: '팀원' }),
    ).not.toBeInTheDocument();
    await step(() =>
      user.click(screen.getByRole('link', { name: '팀 공간으로' })),
    );
    expect(screen.getByRole('heading', { name: '팀원' })).toBeInTheDocument();
    const members = within(screen.getByRole('region', { name: '팀원' }));
    expect(members.getByText(/^팀장/)).toBeInTheDocument();
    expect(
      members.getByLabelText('팀장 포함 팀원 2명, 정원 4명'),
    ).toHaveTextContent('2/4');
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
    expect(screen.getByRole('heading', { name: '팀원' })).toBeInTheDocument();
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
      screen.queryByRole('heading', { name: '팀원' }),
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
    expect(screen.getByRole('heading', { name: '팀원' })).toBeInTheDocument();
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
    expect(
      screen.getByLabelText('팀장 포함 팀원 3명, 정원 4명'),
    ).toHaveTextContent('3/4');
    expect(
      within(screen.getByRole('region', { name: '팀원' })).getByText('김서연'),
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
        ).findByRole('figure', { name: '항목별 평가 점수' }),
      ).toHaveTextContent('100점 기준');
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
  // Codex 리뷰 P1: 계정 전환 후 재조회가 404여도 이전 팀장 계정의 비공개 프로필을 보여 주지 않습니다.
  it('hides a private applicant profile after switching to an account without access', async () => {
    const db = withProfile(publicRecords(), demoIds.accounts.seoyeon, {
      experienceState: 'provided',
      experienceBody: '팀장에게만 보이는 경험',
      isPublic: false,
    });
    const { user, step } = await renderPage(
      `/applicants/${demoIds.applications.seoyeon}`,
      { signedIn: true, db },
    );
    expect(screen.getByText('팀장에게만 보이는 경험')).toBeInTheDocument();
    await step(() =>
      user.click(screen.getByRole('button', { name: '다른 계정으로 전환' })),
    );
    expect(
      screen.getByRole('heading', { name: '지원서를 확인할 수 없어요' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('팀장에게만 보이는 경험'),
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

describe('explicit applicant decisions', () => {
  const path = `/applicants/${demoIds.applications.seoyeon}`;
  const records = (status: ApplicationStatus = 'submitted') => {
    const db = publicRecords();
    const application = db.applications.find(
      (item) => item.id === demoIds.applications.seoyeon,
    )!;
    application.status = status;
    application.discardReason =
      status === 'discarded' ? 'selected_elsewhere' : null;
    return db;
  };
  const current = () =>
    mockDb().applications.find(
      (item) => item.id === demoIds.applications.seoyeon,
    )!;
  const writes = (action: string) =>
    sentRequests.filter(
      (request) =>
        request.method === 'PUT' && request.path.endsWith(`/${action}`),
    );

  it('keeps reads unchanged and starts review only after the leader clicks', async () => {
    const { user, step } = await renderPage(
      `/teams/${demoIds.teams.greenwave}?view=applicants`,
      { signedIn: true, db: records() },
    );
    expect(current().status).toBe('submitted');
    await step(() =>
      user.click(
        screen.getByRole('link', { name: '김서연 지원서 검토, 시연 계정' }),
      ),
    );
    expect(current().status).toBe('submitted');
    expect(writes('review-start')).toHaveLength(0);
    const memberships = structuredClone(mockDb().memberships);
    const notifications = mockDb().notifications.length;
    await step(() =>
      user.click(screen.getByRole('button', { name: '검토 시작' })),
    );
    expect(current().status).toBe('reviewing');
    expect(
      within(screen.getByRole('region', { name: '검토 결과' })).getByRole(
        'status',
      ),
    ).toHaveTextContent('검토를 시작했어요');
    expect(
      screen.queryByRole('button', { name: '검토 시작' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '미선발 처리' })).toBeEnabled();
    expect(mockDb().memberships).toEqual(memberships);
    expect(mockDb().notifications).toHaveLength(notifications + 1);
    expect(writes('review-start')).toHaveLength(1);
  });

  it('confirms direct rejection, explains reapplication and preserves state on cancel', async () => {
    const { user, step } = await renderPage(path, {
      signedIn: true,
      db: records(),
    });
    await user.click(screen.getByRole('button', { name: '미선발 처리' }));
    expect(
      within(screen.getByRole('dialog')).getByText(
        /이 팀에 다시 지원할 수 없어요/,
      ),
    ).toBeInTheDocument();
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '돌아가기',
      }),
    );
    expect(current().status).toBe('submitted');
    expect(writes('rejection')).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: '미선발 처리' }));
    await step(() =>
      user.click(
        within(screen.getByRole('dialog')).getByRole('button', {
          name: '미선발로 확정',
        }),
      ),
    );
    expect(current().status).toBe('rejected');
    expect(screen.getByText('미선발된 지원서예요.')).toBeInTheDocument();
    expect(writes('review-start')).toHaveLength(0);
    expect(writes('rejection')).toHaveLength(1);
  });

  it.each(['closed', 'full', 'closed-full'] as const)(
    'allows rejection of a reviewing applicant when the contest or team is %s',
    async (condition) => {
      const db = records('reviewing');
      if (condition !== 'full') {
        const contest = db.contests.find(
          (item) => item.id === demoIds.contests.green,
        )!;
        contest.startsAt = '2026-08-31T15:00:00Z';
        contest.timing.startsAt = contest.startsAt;
        contest.timing.openSourceDate = '2026-09-01';
        contest.endsAt = '2026-09-30T15:00:00Z';
        contest.timing.endsAt = contest.endsAt;
        contest.timing.closing.sourceDate = '2026-09-30';
      }
      if (condition !== 'closed') {
        const team = db.teams.find(
          (item) => item.id === demoIds.teams.greenwave,
        )!;
        team.capacity = '2';
        team.recruitmentState = 'closed';
        team.closedReason = 'capacity_reached';
      }
      const { user, step } = await renderPage(path, { signedIn: true, db });
      expect(current().status).toBe('reviewing');
      expect(
        screen.queryByRole('button', { name: '이 지원자 선발하기' }),
      ).not.toBeInTheDocument();
      if (condition !== 'full')
        expect(
          screen.getByText(/공고 접수가 마감되어 선발할 수 없어요/),
        ).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: '미선발 처리' }));
      await step(() =>
        user.click(
          within(screen.getByRole('dialog')).getByRole('button', {
            name: '미선발로 확정',
          }),
        ),
      );
      expect(current().status).toBe('rejected');
    },
  );

  it.each(['selected', 'rejected', 'canceled', 'discarded'] as const)(
    'does not offer review or rejection for %s applications',
    async (status) => {
      await renderPage(path, { signedIn: true, db: records(status) });
      expect(
        screen.queryByRole('button', { name: '검토 시작' }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: '미선발 처리' }),
      ).not.toBeInTheDocument();
      expect(writes('review-start')).toHaveLength(0);
      expect(writes('rejection')).toHaveLength(0);
    },
  );

  it('refetches the version after a conflict without retrying the decision automatically', async () => {
    const { user, step } = await renderPage(path, {
      signedIn: true,
      db: records(),
    });
    const loaded = current().version;
    current().version = String(Number(loaded) + 1);
    const latest = current().version;
    await step(() =>
      user.click(screen.getByRole('button', { name: '검토 시작' })),
    );
    expect(screen.getByRole('alert')).toHaveTextContent(
      '최신 지원 상태를 확인한 뒤 다시 시도해 주세요',
    );
    expect(current().status).toBe('submitted');
    expect(writes('review-start').map((request) => request.body)).toEqual([
      { expectedVersion: loaded },
    ]);
    await step(() =>
      user.click(screen.getByRole('button', { name: '검토 시작' })),
    );
    expect(writes('review-start').map((request) => request.body)).toEqual([
      { expectedVersion: loaded },
      { expectedVersion: latest },
    ]);
    expect(current().status).toBe('reviewing');
  });

  it('keeps a failed rejection open and uses the refreshed version after confirmation', async () => {
    const { user, step } = await renderPage(path, {
      signedIn: true,
      db: records('reviewing'),
    });
    const loaded = current().version;
    current().version = String(Number(loaded) + 1);
    const latest = current().version;
    await user.click(screen.getByRole('button', { name: '미선발 처리' }));
    const confirm = () =>
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '미선발로 확정',
      });
    await step(() => user.click(confirm()));
    expect(
      within(screen.getByRole('dialog')).getByRole('alert'),
    ).toHaveTextContent('최신 지원 상태를 확인한 뒤 다시 시도해 주세요');
    expect(writes('rejection')).toHaveLength(1);
    await step(() => user.click(confirm()));
    expect(writes('rejection').map((request) => request.body)).toEqual([
      { expectedVersion: loaded },
      { expectedVersion: latest },
    ]);
    expect(current().status).toBe('rejected');
  });

  it('blocks repeated and competing decisions while review is pending', async () => {
    const { user, client } = await renderPage(path, {
      signedIn: true,
      db: records(),
    });
    const fetch = globalThis.fetch;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal('fetch', async (input: string, init?: RequestInit) => {
      if (input.endsWith('/review-start')) await gate;
      return fetch(input, init);
    });
    const button = screen.getByRole('button', {
      name: '검토 시작',
    });
    try {
      await user.click(button);
      expect(
        screen.getByRole('button', { name: '검토 시작 중…' }),
      ).toBeDisabled();
      expect(
        screen.getByRole('button', { name: '미선발 처리' }),
      ).toBeDisabled();
      expect(
        screen.getByRole('button', { name: '이 지원자 선발하기' }),
      ).toBeDisabled();
      await user.click(button);
    } finally {
      await act(async () => release());
      await settled(client);
    }
    expect(writes('review-start')).toHaveLength(1);
  });

  it('hides cached private details when the leader loses permission during a decision', async () => {
    const { user, step } = await renderPage(path, {
      signedIn: true,
      db: withProfile(records(), demoIds.accounts.seoyeon, { isPublic: false }),
    });
    mockDb().teams.find(
      (item) => item.id === demoIds.teams.greenwave,
    )!.ownerAccountId = demoIds.accounts.doyun;
    await step(() =>
      user.click(screen.getByRole('button', { name: '검토 시작' })),
    );
    expect(
      screen.getByRole('heading', { name: '지원서를 확인할 수 없어요' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(seoyeonProfile.experienceBody!),
    ).not.toBeInTheDocument();
    expect(current().status).toBe('submitted');
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

  it('keeps full-team reopening unavailable across tabs and gives no management action to a member', async () => {
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
    await view.step(() =>
      view.user.click(screen.getByRole('link', { name: '지원자 관리' })),
    );
    expect(
      screen.queryByRole('button', { name: '다시 모집하기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('팀 정원이 모두 차서 다시 모집할 수 없어요.'),
    ).not.toBeInTheDocument();
    expect(sentRequests.filter(failReopen)).toHaveLength(0);
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
    expect(
      within(screen.getByRole('region', { name: '지원자 관리' })).getAllByRole(
        'link',
        { name: /지원서 검토/ },
      ),
    ).toHaveLength(1);
    expect(
      screen.queryByText('같은 공모전의 다른 팀에서 선발됨'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('폐기')).not.toBeInTheDocument();
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
      ).findByRole('figure', { name: '항목별 평가 점수' }),
    ).toHaveTextContent('100점 기준');
    expect(
      screen.getByText(/폐기된 지원은 새 선발 후보 추천에서 제외/),
    ).toBeInTheDocument();
  });
});

// Codex 리뷰 P2: 409 뒤 최신 버전을 다시 받아, 사용자가 다시 누르면 새 버전으로 보냅니다(docs/api/conventions.md#versioned-action).
describe('version conflicts', () => {
  // 화면이 조회한 뒤 다른 변경으로 서버 버전이 올라간 상태
  const bumpVersion = (item: { version: string }) => {
    item.version = String(Number(item.version) + 1);
    return item.version;
  };

  it('closes recruitment with the refreshed team version after a 409', async () => {
    const { user, step } = await renderPage(
      `/teams/${demoIds.teams.greenwave}?view=space`,
      { signedIn: true, db: publicRecords() },
    );
    const team = mockDb().teams.find(
      (item) => item.id === demoIds.teams.greenwave,
    )!;
    const loaded = team.version;
    const latest = bumpVersion(team);
    const closure = () =>
      sentRequests.filter((request) =>
        request.path.endsWith('/recruitment/closure'),
      );
    await user.click(screen.getByRole('button', { name: '모집 종료' }));
    const confirm = () =>
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '모집 종료하기',
      });
    await step(() => user.click(confirm()));
    expect(
      within(screen.getByRole('dialog')).getByRole('alert'),
    ).toHaveTextContent('처리하지 못했어요');
    // 자동 재전송 없음
    expect(closure().map((request) => request.body)).toEqual([
      { expectedVersion: loaded },
    ]);
    await step(() => user.click(confirm()));
    expect(closure().map((request) => request.body)).toEqual([
      { expectedVersion: loaded },
      { expectedVersion: latest },
    ]);
    expect(
      within(screen.getByRole('region', { name: '모집 관리' })).getByRole(
        'status',
      ),
    ).toHaveTextContent('모집을 종료했어요');
  });

  it('cancels an application with the refreshed application version after a 409', async () => {
    const { user, step } = await renderPage('/workspace?view=applications', {
      signedIn: true,
    });
    const application = mockDb().applications.find(
      (item) => item.id === demoIds.applications.localcrew,
    )!;
    const loaded = application.version;
    const latest = bumpVersion(application);
    const cancellation = () =>
      sentRequests.filter((request) => request.path.endsWith('/cancellation'));
    await user.click(screen.getByRole('button', { name: '지원 취소' }));
    const confirm = () =>
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '지원 취소하기',
      });
    await step(() => user.click(confirm()));
    expect(
      within(screen.getByRole('dialog')).getByRole('alert'),
    ).toBeInTheDocument();
    await step(() => user.click(confirm()));
    expect(cancellation().map((request) => request.body)).toEqual([
      { expectedVersion: loaded },
      { expectedVersion: latest },
    ]);
    expect(
      screen.getByText(
        '지원이 취소됐어요. 현재 모집 조건이 맞으면 다시 지원할 수 있어요.',
      ),
    ).toBeInTheDocument();
  });
});

describe('demo identity labels', () => {
  it('labels the team independently from its real contest', async () => {
    const db = publicRecords();
    const team = db.teams.find((item) => item.id === demoIds.teams.greenwave)!;
    const contest = db.contests.find((item) => item.id === team.contestId)!;
    contest.id = '12345678-0000-4000-8000-000000000001';
    team.contestId = contest.id;
    await renderPage(`/teams/${team.id}`, { db });
    expect(screen.getByText('시연 팀')).toBeInTheDocument();
    expect(screen.queryByText('시연 공고')).not.toBeInTheDocument();
  });

  it('does not classify a real team by its demo-looking name', async () => {
    const db = publicRecords();
    const team = db.teams.find((item) => item.id === demoIds.teams.greenwave)!;
    const originalId = team.id;
    team.id = '12345678-0000-4000-8000-000000000002';
    for (const member of db.memberships) {
      if (member.teamId === originalId) member.teamId = team.id;
    }
    team.name = '시연 테스트 팀';
    await renderPage(`/teams/${team.id}`, { db });
    expect(screen.queryByText('시연 팀')).not.toBeInTheDocument();
    expect(screen.getByText('시연 공고')).toBeInTheDocument();
  });

  it('labels workspace team links and application targets', async () => {
    const { user, step } = await renderPage('/workspace', { signedIn: true });
    const link = screen.getByRole('link', { name: /그린웨이브.*팀 공간으로/ });
    expect(link).toHaveAccessibleName(/시연 팀/);
    expect(within(link).getByText('시연 팀')).toBeInTheDocument();
    await step(() => user.click(screen.getByRole('link', { name: '내 지원' })));
    expect(screen.getAllByText('시연 팀').length).toBeGreaterThan(0);
  });

  it('labels applicants in the list, profile and selection confirmation', async () => {
    const { user, step } = await renderPage(
      `/teams/${demoIds.teams.greenwave}?view=applicants`,
      { signedIn: true },
    );
    const link = screen.getByRole('link', { name: /김서연.*지원서 검토/ });
    expect(link).toHaveAccessibleName(/시연 계정/);
    await step(() => user.click(link));
    expect(
      within(screen.getByRole('region', { name: '김서연' })).getByText(
        '시연 계정',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('시연 팀')).toBeInTheDocument();
    expect(screen.getByText('교내 미인증')).toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: '이 지원자 선발하기' }),
    );
    expect(screen.getByRole('dialog')).toHaveAccessibleDescription(/시연 계정/);
    expect(
      sentRequests.filter(
        (request) =>
          request.method === 'PUT' && request.path.includes('/selection'),
      ),
    ).toHaveLength(0);
  });

  it('labels a private member without exposing the hidden profile', async () => {
    const db = withProfile(publicRecords(), ME, {
      isPublic: false,
      experienceState: 'provided',
      experienceBody: '비공개 경력은 표시하지 않음',
    });
    db.account.id = demoIds.accounts.haneul;
    await renderPage(`/teams/${demoIds.teams.greenwave}?view=space`, {
      signedIn: true,
      db,
    });
    const members = within(screen.getByRole('region', { name: '팀원' }));
    const hiddenMember = members
      .getByText(
        db.profiles.find((profile) => profile.accountId === ME)!.realName,
      )
      .closest('li')!;
    expect(within(hiddenMember).getByText('시연 계정')).toBeInTheDocument();
    expect(
      screen.queryByText('비공개 경력은 표시하지 않음'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '모집 종료' }),
    ).not.toBeInTheDocument();
  });
});

it('keeps a real applicant unlabelled in review and rejection confirmation', async () => {
  const db = withProfile(publicRecords(), demoIds.accounts.seoyeon, {
    isDemo: false,
    realName: '시연이라는 이름',
  });
  const { user } = await renderPage(
    `/applicants/${demoIds.applications.seoyeon}`,
    { signedIn: true, db },
  );
  expect(
    screen.getByRole('region', { name: '시연이라는 이름' }),
  ).toBeInTheDocument();
  expect(screen.queryByText('시연 계정')).not.toBeInTheDocument();
  expect(screen.getByText('시연 팀')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '미선발 처리' }));
  expect(screen.getByRole('dialog')).not.toHaveAccessibleDescription(
    /시연 계정/,
  );
});
