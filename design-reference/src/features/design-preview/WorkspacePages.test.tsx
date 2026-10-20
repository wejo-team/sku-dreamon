import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import {
  initialApplicants,
  initialApplications,
  initialProfile,
  initialTeams,
  previewPath,
} from './data';
import { PreviewProvider } from './PreviewProvider';
import {
  PreviewContext,
  type PreviewState,
  usePreview,
} from './preview-context';
import { ApplicantPage, TeamPage, WorkspacePage } from './WorkspacePages';
import { CreateTeamPage } from './CreateTeamPage';
import { lifecycleReferenceActivity } from './lifecycle-fixtures';

function TestControls() {
  const { signOut, signIn, emptyWorkspace, profile, saveProfile } =
    usePreview();
  return (
    <>
      <button onClick={signOut}>테스트 로그아웃</button>
      <button onClick={signIn}>테스트 로그인</button>
      <button onClick={emptyWorkspace}>테스트 비우기</button>
      <button
        onClick={() =>
          saveProfile({ ...profile, visibility: { discoverable: true } })
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
function renderPage(path: string, state?: PreviewState) {
  const content = (
    <MemoryRouter initialEntries={[path]}>
      <TestControls />
      <CurrentLocation />
      <Routes>
        <Route path="/design-preview/explore" element={<p>팀 탐색 목록</p>} />
        <Route path="/design-preview/teams/new" element={<CreateTeamPage />} />
        <Route path="/design-preview/teams/:teamId" element={<TeamPage />} />
        <Route path="/design-preview/workspace" element={<WorkspacePage />} />
        <Route
          path="/design-preview/applicants/:applicantId"
          element={<ApplicantPage />}
        />
      </Routes>
    </MemoryRouter>
  );
  return render(
    state ? (
      <PreviewContext value={state}>{content}</PreviewContext>
    ) : (
      <PreviewProvider>{content}</PreviewProvider>
    ),
  );
}
function previewState(overrides: Partial<PreviewState> = {}): PreviewState {
  return {
    signedIn: true,
    notifications: [],
    markNotificationsRead: vi.fn(),
    profile: { ...initialProfile, visibility: { discoverable: true } },
    teams: initialTeams,
    applicants: initialApplicants,
    applications: initialApplications,
    signIn: vi.fn(),
    signOut: vi.fn(),
    saveProfile: vi.fn(),
    apply: vi.fn().mockReturnValue(false),
    selectApplicant: vi.fn().mockReturnValue(false),
    cancelApplication: vi.fn().mockReturnValue(false),
    closeRecruitment: vi.fn().mockReturnValue(false),
    reopenRecruitment: vi.fn().mockReturnValue(false),
    createTeam: vi.fn().mockReturnValue('new-team'),
    reset: vi.fn(),
    emptyWorkspace: vi.fn(),
    ...overrides,
  };
}

describe('team application', () => {
  it('accepts an unadvertised role and links the new application to its result', async () => {
    const user = userEvent.setup();
    renderPage(previewPath('/teams/makers'));
    await user.click(screen.getByRole('button', { name: '테스트 로그인' }));
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
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '공개로 전환',
      }),
    );
    expect(screen.queryByText('지원이 완료됐어요')).not.toBeInTheDocument();
    expect(
      screen.getByText(/AI 검토에 최신 프로필을 사용할 수 있어요/),
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
    expect(
      await screen.findByRole('button', { name: '지원하는 중…' }),
    ).toBeDisabled();
    expect(await screen.findByText('지원이 완료됐어요')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: '내 지원 확인하기' }));
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
  it('gates missing required profile fields and preserves the target team', () => {
    renderPage(
      previewPath('/teams/makers'),
      previewState({ profile: { ...initialProfile, interests: [] } }),
    );
    expect(
      screen.getByText('지원 전에 프로필을 완성해 주세요'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '프로필 보완하기' }),
    ).toHaveAttribute(
      'href',
      `${previewPath('/profile')}?edit=details&returnTo=${encodeURIComponent(previewPath('/teams/makers'))}`,
    );
    expect(
      screen.queryByRole('button', { name: '이 팀에 지원하기' }),
    ).not.toBeInTheDocument();
  });
  it('preserves written text after failure and rejects a logged-out delayed submission', async () => {
    const user = userEvent.setup();
    const failed = previewState();
    const view = renderPage(previewPath('/teams/makers'), failed);
    await user.click(screen.getByRole('radio', { name: '디자인' }));
    await user.type(
      screen.getByLabelText(/팀에 전할 말/),
      '화면 설계를 맡고 싶어요.',
    );
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    expect(
      await screen.findByText(/지원을 완료하지 못했어요/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/팀에 전할 말/)).toHaveValue(
      '화면 설계를 맡고 싶어요.',
    );
    view.unmount();
    renderPage(previewPath('/teams/makers'));
    await user.click(screen.getByRole('button', { name: '테스트 로그인' }));
    await user.click(screen.getByRole('button', { name: '테스트 공개' }));
    await user.click(screen.getByRole('radio', { name: '기획' }));
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    await user.click(screen.getByRole('button', { name: '테스트 로그아웃' }));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 400));
    });
    expect(
      screen.getByRole('link', { name: '로그인하고 지원하기' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('지원이 완료됐어요')).not.toBeInTheDocument();
  });
  it('preserves an over-limit application message and accepts the 1,000-codepoint boundary', async () => {
    const user = userEvent.setup();
    const apply = vi.fn().mockReturnValue(false);
    renderPage(previewPath('/teams/makers'), previewState({ apply }));
    await user.click(screen.getByRole('radio', { name: '디자인' }));
    const field = screen.getByLabelText(/팀에 전할 말/);
    await user.click(field);
    await user.paste('🎨'.repeat(1001));
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    expect(
      await screen.findByText('팀에 전할 말은 1,000자까지 입력할 수 있어요.'),
    ).toBeInTheDocument();
    expect(field).toHaveValue('🎨'.repeat(1001));
    expect(apply).not.toHaveBeenCalled();
    await user.clear(field);
    await user.paste('🎨'.repeat(1000));
    await user.click(screen.getByRole('button', { name: '이 팀에 지원하기' }));
    await screen.findByText(/지원을 완료하지 못했어요/);
    expect(apply).toHaveBeenCalledWith('makers', '디자인', '🎨'.repeat(1000));
  });
  it('keeps public recruitment separate from the private team space', async () => {
    const user = userEvent.setup();
    renderPage(previewPath('/teams/greenwave'), previewState());
    expect(
      screen.getByRole('heading', { name: '모집 정보' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '확정된 팀원' }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: '팀 공간으로' }));
    expect(
      screen.getByRole('heading', { name: '확정된 팀원' }),
    ).toBeInTheDocument();
    expect(screen.getByText('내 역할').parentElement).toHaveTextContent('팀장');
  });
  it('preserves filtered return destinations and rejects external ones', () => {
    const from = previewPath('/explore?tab=teams&role=디자인&q=캠퍼스');
    const view = renderPage(
      `${previewPath('/teams/makers')}?from=${encodeURIComponent(from)}`,
    );
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute(
      'href',
      from,
    );
    view.unmount();
    renderPage(
      `${previewPath('/teams/makers')}?from=${encodeURIComponent('https://example.com')}`,
    );
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute(
      'href',
      previewPath('/explore?tab=teams'),
    );
  });
});

describe('workspace membership and access', () => {
  it('shows leader and member teams but hides activity before login', async () => {
    const user = userEvent.setup();
    renderPage(previewPath('/workspace'));
    expect(screen.queryByText('그린웨이브')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '테스트 로그인' }));
    expect(
      screen.getByRole('heading', { name: '그린웨이브' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: '로컬 크루' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '테스트 비우기' }));
    expect(screen.getByText('함께할 첫 팀을 찾아보세요')).toBeInTheDocument();
  });
  it('allows members to view the team but does not grant management rights', () => {
    const view = renderPage(
      previewPath('/teams/localcrew?view=space'),
      previewState(),
    );
    expect(
      screen.getByRole('heading', { name: '확정된 팀원' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '지원자 관리' }),
    ).not.toBeInTheDocument();
    view.unmount();
    renderPage(previewPath('/teams/localcrew?view=applicants'), previewState());
    expect(
      screen.getByText('팀장만 지원서를 볼 수 있어요'),
    ).toBeInTheDocument();
  });
  it('revokes team-space access after a selected member cancels', async () => {
    const user = userEvent.setup();
    renderPage(previewPath('/workspace?view=applications'));
    await user.click(screen.getByRole('button', { name: '테스트 로그인' }));
    await user.click(screen.getByRole('button', { name: '지원 취소' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText(/팀 공간에 접근할 수 없게/)).toBeInTheDocument();
    await user.click(dialog.getByRole('button', { name: '지원 취소하기' }));
    expect(
      screen.getByText(
        '지원이 취소됐어요. 현재 모집 조건이 맞으면 다시 지원할 수 있어요.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '팀 공간으로' }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: '내 팀으로' }));
    expect(
      screen.queryByRole('heading', { name: '로컬 크루' }),
    ).not.toBeInTheDocument();
  });
  it('rejects direct private-space access for a nonmember', () => {
    renderPage(previewPath('/teams/makers?view=space'), previewState());
    expect(
      screen.getByText('현재 팀원만 팀 공간에 들어갈 수 있어요'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '확정된 팀원' }),
    ).not.toBeInTheDocument();
  });
  it('requires confirmation to close recruitment and keeps the current team', async () => {
    const user = userEvent.setup();
    renderPage(previewPath('/teams/greenwave?view=space'));
    await user.click(screen.getByRole('button', { name: '테스트 로그인' }));
    await user.click(screen.getByRole('button', { name: '모집 종료' }));
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '모집 종료하기',
      }),
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
    const user = userEvent.setup();
    renderPage(previewPath('/applicants/app-seoyeon'));
    await user.click(screen.getByRole('button', { name: '테스트 로그인' }));
    const profile = within(screen.getByRole('region', { name: '김서연' }));
    const applicantProfile = initialApplicants[0]!.profile!;
    expect(profile.getByText('경험')).toBeInTheDocument();
    expect(profile.getByText(applicantProfile.experience)).toBeInTheDocument();
    expect(profile.getByText(applicantProfile.intro)).toBeInTheDocument();
    expect(
      profile.getByRole('link', { name: /김서연의 프로젝트\s*\(새 창\)/ }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: '이 지원자 선발하기' }),
    );
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText(/즉시 팀원이 확정/)).toBeInTheDocument();
    await user.click(
      dialog.getByRole('button', { name: '선발하고 팀원 확정' }),
    );
    expect(
      screen.getByText('김서연 님이 팀원으로 확정됐어요'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: '팀 공간으로' }));
    expect(screen.getByText('확정').parentElement).toHaveTextContent('3 / 4명');
    expect(
      within(screen.getByRole('region', { name: '확정된 팀원' })).getByText(
        '김서연',
      ),
    ).toBeInTheDocument();
  });
  it('shows a private applicant’s full registered profile to the applied team leader', () => {
    const applicants = [
      {
        ...initialApplicants[0]!,
        profile: {
          ...initialProfile,
          intro: '지원자의 자기소개',
          experienceState: 'provided' as const,
          experience: '지원자의 경험',
          academicStatus: '재학',
          grade: '3학년',
          college: '이공대학',
          department: '소프트웨어학과',
          major: '컴퓨터공학',
          skills: ['개발'],
          interests: ['교육'],
          availability: '5~10시간 미만',
          visibility: { discoverable: false },
          portfolio: 'https://example.com/secret',
          portfolioTitle: '지원자의 포트폴리오',
        },
      },
    ];
    renderPage(
      previewPath('/applicants/app-seoyeon'),
      previewState({ applicants }),
    );
    for (const value of [
      '지원자의 자기소개',
      '지원자의 경험',
      '재학',
      '3학년',
      '이공대학',
      '소프트웨어학과',
      '컴퓨터공학',
      '개발',
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
  it.each(['모집마감', '팀원확정'] as const)(
    'allows AI review for existing applicants while %s',
    async (status) => {
      const user = userEvent.setup();
      renderPage(
        previewPath('/applicants/app-seoyeon'),
        previewState({
          teams: initialTeams.map((team) =>
            team.id === 'greenwave'
              ? { ...team, status, members: team.capacity }
              : team,
          ),
        }),
      );
      expect(
        screen.queryByRole('button', { name: '이 지원자 선발하기' }),
      ).not.toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
      expect(
        await within(
          screen.getByRole('region', { name: 'AI 검토 도움' }),
        ).findByRole('status'),
      ).toHaveTextContent(initialApplicants[0]!.message);
      expect(
        screen.getByRole('button', { name: '다시 검토하기' }),
      ).toBeEnabled();
    },
  );
  it('does not expose applications to a nonleader', () => {
    renderPage(
      previewPath('/applicants/app-seoyeon'),
      previewState({
        teams: initialTeams.map((team) => ({ ...team, owner: false })),
      }),
    );
    expect(screen.getByText('지원서를 확인할 수 없어요')).toBeInTheDocument();
    expect(screen.queryByText('김서연')).not.toBeInTheDocument();
    expect(
      screen.queryByText(initialApplicants[0]!.profile!.experience),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /김서연의 프로젝트/ }),
    ).not.toBeInTheDocument();
  });
  it('does not expose applicant details before login', () => {
    renderPage(previewPath('/applicants/app-seoyeon'));
    expect(screen.getByText('로그인하고 이어가세요')).toBeInTheDocument();
    expect(screen.queryByText('김서연')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /김서연의 프로젝트/ }),
    ).not.toBeInTheDocument();
  });
});

describe('team creation', () => {
  it('shows capacity and deadline constraints in the official creation flow', async () => {
    const user = userEvent.setup();
    renderPage(previewPath('/teams/new?contestId=campus'), previewState());
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
    const user = userEvent.setup();
    renderPage(previewPath('/teams/greenwave?view=space'));
    await user.click(screen.getByRole('button', { name: '테스트 로그인' }));
    await user.click(screen.getByRole('button', { name: '모집 종료' }));
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '모집 종료하기',
      }),
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
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '모집 중으로 변경',
      }),
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

  it('shows why a full team cannot reopen and gives no management action to a member', () => {
    const teams = initialTeams.map((team) =>
      team.id === 'greenwave'
        ? { ...team, status: '모집마감' as const, members: team.capacity }
        : team,
    );
    const view = renderPage(
      previewPath('/teams/greenwave?view=space'),
      previewState({ teams }),
    );
    expect(
      screen.getByRole('button', { name: '다시 모집하기' }),
    ).toBeDisabled();
    expect(
      screen.getByText('팀 정원이 모두 차서 다시 모집할 수 없어요.'),
    ).toBeInTheDocument();
    view.unmount();
    renderPage(previewPath('/teams/localcrew?view=space'), previewState());
    expect(
      screen.queryByRole('button', { name: '다시 모집하기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '모집 종료' }),
    ).not.toBeInTheDocument();
  });

  it('retains the closed state when a reopen request fails', async () => {
    const user = userEvent.setup();
    const mock = previewState(lifecycleReferenceActivity());
    renderPage(previewPath('/teams/greenwave?view=applicants'), mock);
    await user.click(screen.getByRole('button', { name: '다시 모집하기' }));
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '모집 중으로 변경',
      }),
    );
    expect(mock.reopenRecruitment).toHaveBeenCalledExactlyOnceWith('greenwave');
    expect(
      within(screen.getByRole('dialog')).getByRole('alert'),
    ).toHaveTextContent('처리하지 못했어요');
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '돌아가기',
      }),
    );
    expect(screen.getByText('모집 마감')).toBeInTheDocument();
  });

  it('shows discarded history and reason in my applications without cancellation or team-space access', () => {
    renderPage(
      previewPath('/workspace?view=applications'),
      previewState(lifecycleReferenceActivity()),
    );
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
    const user = userEvent.setup();
    const state = previewState(lifecycleReferenceActivity());
    const view = renderPage(
      previewPath('/teams/greenwave?view=applicants'),
      state,
    );
    expect(screen.getByText('검토 대기 1명')).toBeInTheDocument();
    expect(
      screen.getByText('같은 공모전의 다른 팀에서 선발됨'),
    ).toBeInTheDocument();
    view.unmount();
    renderPage(previewPath('/applicants/app-seoyeon'), state);
    expect(screen.getByText('폐기')).toBeInTheDocument();
    expect(
      screen.getByText(initialApplicants[0]!.profile!.experience),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '이 지원자 선발하기' }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(
      await within(
        screen.getByRole('region', { name: 'AI 검토 도움' }),
      ).findByRole('status'),
    ).toHaveTextContent(initialApplicants[0]!.message);
    expect(
      screen.getByText(/폐기된 지원은 새 선발 후보 추천에서 제외/),
    ).toBeInTheDocument();
  });
});
