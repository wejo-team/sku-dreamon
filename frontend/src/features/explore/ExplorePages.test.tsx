import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import {
  ContestPage,
  ExplorePage,
  PersonPage,
} from '@/features/explore/ExplorePages';
import { TeamPage } from '@/features/workspace/WorkspacePages';
import {
  archivedContest,
  contests,
  initialProfile,
  initialTeams,
  people,
  type Profile,
  type Team,
} from '@/features/demo/data';
import { DemoContext, type DemoState } from '@/features/demo/demo-context';

function CurrentLocation() {
  const { pathname, search } = useLocation();
  return <p aria-label="현재 경로">{pathname + search}</p>;
}

function currentUrl() {
  return new URL(
    screen.getByLabelText('현재 경로').textContent!,
    'https://example.com',
  );
}

function renderExplore(path: string, overrides: Partial<DemoState> = {}) {
  const state: DemoState = {
    signedIn: false,
    profile: initialProfile,
    teams: initialTeams,
    applications: [],
    applicants: [],
    notifications: [],
    markNotificationsRead: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
    saveProfile: vi.fn(),
    apply: vi.fn(() => true),
    selectApplicant: vi.fn(() => true),
    cancelApplication: vi.fn(() => true),
    closeRecruitment: vi.fn(() => true),
    reopenRecruitment: vi.fn(() => true),
    createTeam: vi.fn(() => 'created'),
    reset: vi.fn(),
    emptyWorkspace: vi.fn(),
    ...overrides,
  };
  render(
    <MemoryRouter initialEntries={[path]}>
      <DemoContext value={state}>
        <CurrentLocation />
        <Routes>
          <Route path="/explore" element={<ExplorePage />} />
          <Route path="/people/:personId" element={<PersonPage />} />
          <Route path="/contests/:contestId" element={<ContestPage />} />
          <Route path="/teams/:teamId" element={<TeamPage />} />
        </Routes>
      </DemoContext>
    </MemoryRouter>,
  );
  return state;
}

const publicProfile: Profile = {
  ...initialProfile,
  name: '공개검색검증사용자',
  academicStatus: '재학',
  grade: '3학년',
  college: '융합과학대학',
  department: '디지털미디어학과',
  major: '콘텐츠공학전공',
  skills: ['프로토타이핑'],
  intro: '사용자인터뷰를 함께 진행하고 싶어요.',
  experience: '졸업전시기획 프로젝트',
  experienceState: 'provided',
  availability: '5~10시간 미만',
  portfolioTitle: '캠퍼스작업집',
  portfolio: 'https://portfolio.example.com/jiwoo',
  visibility: { discoverable: true },
};

const pagedTeams: Team[] = Array.from({ length: 14 }, (_, index) => ({
  ...initialTeams[0]!,
  id: `paged-${index + 1}`,
  name: `페이지 팀 ${String(index + 1).padStart(2, '0')}`,
  roles: ['개발', '디자인'],
}));

describe('official reference public exploration', () => {
  it('allows guests to read and filter public contests using the shared interests', async () => {
    renderExplore('/explore');
    expect(
      screen.getByRole('heading', { name: contests[0]!.title }),
    ).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '탐색 필터' }));
    await user.click(screen.getByRole('radio', { name: '교육' }));
    await user.click(screen.getByRole('button', { name: '필터 적용' }));
    expect(screen.getByRole('status')).toHaveTextContent('검색 결과 2개');
    expect(
      screen.getByRole('heading', { name: contests[0]!.title }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: contests[1]!.title }),
    ).not.toBeInTheDocument();
  });

  it('discards filter drafts and clears applied filters while retaining the selected tab', async () => {
    renderExplore('/explore?tab=teams&role=개발&open=true');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '탐색 필터' }));
    await user.click(screen.getByRole('radio', { name: '디자인' }));
    await user.click(screen.getByRole('button', { name: '취소' }));
    await user.click(screen.getByRole('button', { name: '탐색 필터' }));
    expect(screen.getByRole('radio', { name: '개발' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '모집중만' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: '취소' }));
    await user.click(screen.getByRole('button', { name: '검색 조건 초기화' }));
    expect(screen.getByRole('link', { name: '팀' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await user.click(screen.getByRole('button', { name: '탐색 필터' }));
    expect(screen.getByRole('radio', { name: '모든 역할' })).toBeChecked();
    expect(
      screen.getByRole('checkbox', { name: '모집중만' }),
    ).not.toBeChecked();
  });

  it('exposes an accessible AI shortcut and resets a sort-only condition', async () => {
    renderExplore('/explore?sort=deadline');
    expect(
      screen.getByRole('link', { name: 'AI에게 추천 받기' }),
    ).toHaveAttribute('href', '/ai');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '검색 조건 초기화' }));
    expect(screen.getByLabelText('정렬')).toHaveValue('default');
    expect(
      screen.queryByRole('button', { name: '검색 조건 초기화' }),
    ).not.toBeInTheDocument();
  });

  it('keeps public team recruitment visible to guests without exposing team space', () => {
    const state = renderExplore('/explore?tab=teams');
    const link = screen.getByRole('link', { name: /캠퍼스 메이커스/ });
    expect(link).toHaveAttribute(
      'href',
      '/teams/makers?from=%2Fexplore%3Ftab%3Dteams',
    );
    expect(
      screen.queryByRole('link', { name: /팀 공간/ }),
    ).not.toBeInTheDocument();
    expect(state.apply).not.toHaveBeenCalled();
  });

  it('paginates the complete filtered result and preserves its conditions and page through team detail', async () => {
    const params = new URLSearchParams({
      tab: 'teams',
      q: '페이지',
      role: '개발',
      open: 'true',
      contest: 'campus',
      page: '2',
    });
    renderExplore(`/explore?${params}`, {
      teams: [...pagedTeams, initialTeams[1]!],
    });
    const user = userEvent.setup();
    const nav = screen.getByRole('navigation', { name: '탐색 결과 페이지' });
    expect(screen.getByRole('status')).toHaveTextContent('검색 결과 14개');
    expect(
      screen
        .getAllByRole('heading', { level: 3 })
        .map((node) => node.textContent),
    ).toEqual(pagedTeams.slice(6, 12).map((team) => team.name));
    expect(within(nav).getByRole('link', { name: '2페이지' })).toHaveAttribute(
      'aria-current',
      'page',
    );

    await user.click(within(nav).getByRole('link', { name: '다음 페이지' }));
    expect(
      screen
        .getAllByRole('heading', { level: 3 })
        .map((node) => node.textContent),
    ).toEqual(pagedTeams.slice(12).map((team) => team.name));
    expect(
      screen.getByRole('heading', { name: '함께 도전하는 팀' }),
    ).toHaveFocus();
    const expectedLastPage = new URLSearchParams(params);
    expectedLastPage.set('page', '3');
    expect(currentUrl().searchParams.toString()).toBe(
      expectedLastPage.toString(),
    );
    expect(screen.getByRole('button', { name: '다음 페이지' })).toBeDisabled();

    await user.click(screen.getByRole('link', { name: '이전 페이지' }));
    const listPath = currentUrl().pathname + currentUrl().search;
    const teamLink = screen.getByRole('link', { name: /페이지 팀 07/ });
    expect(
      new URL(
        teamLink.getAttribute('href')!,
        'https://example.com',
      ).searchParams.get('from'),
    ).toBe(listPath);
    await user.click(teamLink);
    expect(
      screen.getByRole('heading', { name: '페이지 팀 07' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute(
      'href',
      listPath,
    );
    await user.click(screen.getByRole('link', { name: '목록으로' }));
    expect(currentUrl().searchParams.toString()).toBe(params.toString());
    expect(
      screen
        .getAllByRole('heading', { level: 3 })
        .map((node) => node.textContent),
    ).toEqual(pagedTeams.slice(6, 12).map((team) => team.name));
  });

  it.each(['search', 'filter', 'tab', 'reset'])(
    'returns to page one when the user changes %s',
    async (action) => {
      renderExplore('/explore?tab=teams&q=페이지&role=개발&page=2', {
        signedIn: true,
        teams: pagedTeams,
      });
      const user = userEvent.setup();
      expect(currentUrl().searchParams.get('page')).toBe('2');
      if (action === 'search') {
        await user.type(
          screen.getByRole('textbox', { name: '탐색 검색' }),
          ' ',
        );
      } else if (action === 'filter') {
        await user.click(screen.getByRole('button', { name: '탐색 필터' }));
        await user.click(screen.getByRole('radio', { name: '디자인' }));
        await user.click(screen.getByRole('button', { name: '필터 적용' }));
        expect(currentUrl().searchParams.get('role')).toBe('디자인');
      } else if (action === 'tab') {
        await user.click(screen.getByRole('link', { name: '사람' }));
        expect(
          screen.getByRole('heading', { name: '함께할 사람' }),
        ).toBeInTheDocument();
      } else {
        await user.click(
          screen.getByRole('button', { name: '검색 조건 초기화' }),
        );
        expect(currentUrl().searchParams.get('role')).toBeNull();
      }
      expect(currentUrl().searchParams.get('page')).toBeNull();
      expect(screen.getByRole('link', { name: '1페이지' })).toHaveAttribute(
        'aria-current',
        'page',
      );
      if (action !== 'tab') {
        expect(
          screen.getByRole('heading', { name: '페이지 팀 01' }),
        ).toBeInTheDocument();
        expect(
          screen.queryByRole('heading', { name: '페이지 팀 07' }),
        ).not.toBeInTheDocument();
      }
    },
  );

  it.each([
    { requested: '0', expectedPage: 1 },
    { requested: '-2', expectedPage: 1 },
    { requested: 'invalid', expectedPage: 1 },
    { requested: '2.5', expectedPage: 1 },
    { requested: '9007199254740992', expectedPage: 1 },
    { requested: '99', expectedPage: 3 },
  ])(
    'normalizes page=$requested to a reachable page without losing filters',
    ({ requested, expectedPage }) => {
      renderExplore(`/explore?tab=teams&role=개발&page=${requested}`, {
        teams: pagedTeams,
      });
      expect(currentUrl().searchParams.get('page')).toBe(
        expectedPage === 1 ? null : String(expectedPage),
      );
      expect(currentUrl().searchParams.get('tab')).toBe('teams');
      expect(currentUrl().searchParams.get('role')).toBe('개발');
      expect(
        screen.getByRole('link', { name: `${expectedPage}페이지` }),
      ).toHaveAttribute('aria-current', 'page');
      expect(
        screen.getByRole('heading', {
          name: expectedPage === 1 ? '페이지 팀 01' : '페이지 팀 13',
        }),
      ).toBeInTheDocument();
    },
  );

  it('does not expose people or their search matches to guests', () => {
    renderExplore('/explore?tab=people&q=정수아');
    expect(
      screen.getByRole('heading', {
        name: '로그인하고 함께할 사람을 찾아보세요',
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'AI에게 추천 받기' }),
    ).toHaveAttribute('href', '/ai');
    for (const person of people)
      expect(
        screen.queryByRole('heading', { name: person.name }),
      ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인하기' })).toHaveAttribute(
      'href',
      '/login?returnTo=%2Fexplore%3Ftab%3Dpeople',
    );
  });

  it('provides the AI shortcut in people search for both guests and members', async () => {
    renderExplore('/explore?tab=people', { signedIn: true });
    expect(
      screen.getByRole('link', { name: 'AI에게 추천 받기' }),
    ).toHaveAttribute('href', '/ai');
  });

  it('guards direct people detail links and keeps the target for login', () => {
    renderExplore('/people/sua');
    expect(
      screen.getByRole('heading', { name: '로그인이 필요해요' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('정수아')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '희망 역할' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인하기' })).toHaveAttribute(
      'href',
      '/login?returnTo=%2Fpeople%2Fsua',
    );
  });

  it('does not create a public detail for a profile excluded from people exploration', () => {
    renderExplore('/people/me', { signedIn: true });
    expect(
      screen.getByRole('heading', { name: '프로필을 찾을 수 없어요' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(initialProfile.name)).not.toBeInTheDocument();
  });

  it.each(['공개검색검증사용자', '졸업전시기획', 'portfolio.example.com'])(
    'excludes a private profile from search regardless of the matching field: %s',
    (query) => {
      renderExplore(`/explore?tab=people&q=${encodeURIComponent(query)}`, {
        signedIn: true,
        profile: { ...publicProfile, visibility: { discoverable: false } },
      });
      expect(
        screen.getByRole('heading', { name: '검색 결과가 없어요' }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole('heading', { name: publicProfile.name }),
      ).not.toBeInTheDocument();
    },
  );

  it.each([
    '공개검색검증사용자',
    '재학',
    '3학년',
    '융합과학대학',
    '디지털미디어학과',
    '콘텐츠공학전공',
    '프로토타이핑',
    '사용자인터뷰',
    '졸업전시기획',
    '5~10시간 미만',
    '캠퍼스작업집',
    'portfolio.example.com',
  ])(
    'finds a public profile by registered profile information: %s',
    (query) => {
      renderExplore(`/explore?tab=people&q=${encodeURIComponent(query)}`, {
        signedIn: true,
        profile: publicProfile,
      });
      expect(
        screen.getByRole('heading', { name: publicProfile.name }),
      ).toBeInTheDocument();
    },
  );

  it('shows every registered public profile field including the schedule and portfolio link', () => {
    renderExplore('/people/me', {
      signedIn: true,
      profile: publicProfile,
    });
    expect(
      screen.getByRole('heading', { name: publicProfile.name }),
    ).toBeInTheDocument();
    for (const value of [
      publicProfile.academicStatus!,
      publicProfile.grade!,
      publicProfile.college!,
      publicProfile.department!,
      publicProfile.major!,
      ...publicProfile.skills,
      ...publicProfile.interests,
      publicProfile.intro,
      publicProfile.experience,
      publicProfile.availability,
    ])
      expect(screen.getByText(value)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /캠퍼스작업집/ })).toHaveAttribute(
      'href',
      publicProfile.portfolio,
    );
    expect(screen.getByRole('link', { name: /캠퍼스작업집/ })).toHaveAttribute(
      'target',
      '_blank',
    );
  });

  it('keeps closed contest history readable with its source while preventing new participation actions', () => {
    const state = renderExplore('/contests/archive');
    expect(
      screen.getByRole('heading', { name: archivedContest.title }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        '접수가 마감되어 새 팀을 만들거나 지원할 수 없어요. 공고는 계속 확인할 수 있어요.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '공식 공고 확인하기' }),
    ).toHaveAttribute('href', archivedContest.officialUrl);
    expect(
      screen.queryByRole('link', { name: '팀 만들기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '팀 찾기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '준비 모임 만들기' }),
    ).not.toBeInTheDocument();
    expect(state.createTeam).not.toHaveBeenCalled();
  });

  it('shows the official entry size, submission material and dates separately from team recruitment', () => {
    renderExplore('/contests/campus');
    const facts = screen.getByText('공식 참가 인원').closest('dl')!;
    expect(within(facts).getByText('2~5명')).toBeInTheDocument();
    expect(
      within(facts).getByText('아이디어 제안서 PDF · 발표 자료'),
    ).toBeInTheDocument();
    expect(within(facts).getByText('2026-10-01')).toBeInTheDocument();
    expect(within(facts).getByText('2026.11.08')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '공식 공고 확인하기' }),
    ).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('link', { name: '팀 만들기' })).toHaveAttribute(
      'href',
      '/teams/new?contest=campus',
    );
  });

  it('shows only this contest’s teams inline with accessible create and AI icon actions', () => {
    renderExplore('/contests/campus');
    const teamSection = screen.getByRole('region', { name: '함께할 팀' });
    expect(
      within(teamSection).getByRole('link', { name: /캠퍼스 메이커스/ }),
    ).toBeInTheDocument();
    expect(
      within(teamSection).queryByText('그린웨이브'),
    ).not.toBeInTheDocument();
    expect(
      within(teamSection).queryByText('로컬 크루'),
    ).not.toBeInTheDocument();
    expect(
      within(teamSection).queryByText(contests[0]!.title),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '팀 찾기' }),
    ).not.toBeInTheDocument();
    const create = within(teamSection).getByRole('link', { name: '팀 만들기' });
    expect(create).toHaveAttribute('href', '/teams/new?contest=campus');
    expect(create.textContent).toBe('');
    const ai = within(teamSection).getByRole('link', {
      name: 'AI로 팀 찾아보기',
    });
    expect(ai).toHaveAttribute('href', '/ai');
    expect(ai.textContent).toBe('');
  });

  it.each([
    {
      contestId: 'campus',
      action: '팀 만들기',
      prompt: '첫 팀을 만들어 함께 도전해 보세요.',
    },
    {
      contestId: 'local',
      action: '팀 만들기',
      prompt: '첫 팀을 만들어 함께 도전해 보세요.',
    },
  ])(
    'invites users to create the first group when $contestId has no teams',
    ({ contestId, action, prompt }) => {
      renderExplore(`/contests/${contestId}`, { teams: [] });
      const teamSection = screen.getByRole('region', { name: '함께할 팀' });
      expect(
        within(teamSection).getByRole('heading', {
          name: '아직 함께할 팀이 없어요',
        }),
      ).toBeInTheDocument();
      expect(within(teamSection).getByText(prompt)).toBeInTheDocument();
      expect(
        within(teamSection).getByRole('link', { name: action }),
      ).toHaveAttribute('href', `/teams/new?contest=${contestId}`);
      expect(
        within(teamSection).queryByRole('navigation'),
      ).not.toBeInTheDocument();
    },
  );

  it('paginates related teams and returns from a team to the same contest team page and explore context', async () => {
    const from = '/explore?category=교육';
    const params = new URLSearchParams({ from, teamPage: '2' });
    const contestPath = `/contests/campus?${params}`;
    renderExplore(contestPath, { teams: [...pagedTeams, initialTeams[1]!] });
    const user = userEvent.setup();
    const teamSection = screen.getByRole('region', { name: '함께할 팀' });
    expect(
      within(teamSection)
        .getAllByRole('heading', { level: 3 })
        .map((node) => node.textContent),
    ).toEqual(pagedTeams.slice(6, 12).map((team) => team.name));
    expect(
      within(teamSection).getByRole('navigation', {
        name: '공모전 팀 목록 페이지',
      }),
    ).toHaveAccessibleDescription('전체 3페이지 중 2페이지');
    expect(screen.getByRole('link', { name: '탐색으로' })).toHaveAttribute(
      'href',
      from,
    );
    await user.click(
      within(teamSection).getByRole('link', { name: /페이지 팀 07/ }),
    );
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute(
      'href',
      contestPath,
    );
    await user.click(screen.getByRole('link', { name: '목록으로' }));
    expect(currentUrl().searchParams.get('teamPage')).toBe('2');
    expect(currentUrl().searchParams.get('from')).toBe(from);
    expect(
      screen.getByRole('heading', { name: '페이지 팀 07' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '페이지 팀 01' }),
    ).not.toBeInTheDocument();
  });

  it('preserves the existing local team under official capacity rules without a preparation exception', () => {
    renderExplore('/contests/local');
    expect(screen.getByText('2~3명')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '팀 만들기' })).toHaveAttribute(
      'href',
      '/teams/new?contest=local',
    );
    expect(screen.queryByText('개인 참가')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /로컬 크루/ })).toBeInTheDocument();
  });

  it('counts every linked team including full and closed teams', () => {
    renderExplore('/explore');
    const local = screen.getByRole('link', { name: /우리 동네를 새롭게/ });
    expect(local).toHaveTextContent('연결된 팀 1개');
  });

  it('applies recruitment filters to capacity and dates as well as raw team state', () => {
    const base = initialTeams[0]!;
    renderExplore('/explore?tab=teams&open=true', {
      teams: [
        {
          ...base,
          id: 'available',
          name: '검토 중 지원 가능',
          status: '지원자검토',
        },
        { ...base, id: 'full', name: '가득 찬 팀', members: 4 },
        {
          ...base,
          id: 'expired',
          name: '기한 지난 팀',
          recruitmentDeadline: '2026-10-17',
        },
        { ...base, id: 'future', name: '시작 전 팀', contestId: 'upcoming' },
      ],
    });
    expect(
      screen.getByRole('heading', { name: '검토 중 지원 가능' }),
    ).toBeInTheDocument();
    for (const name of ['가득 찬 팀', '기한 지난 팀', '시작 전 팀'])
      expect(screen.queryByRole('heading', { name })).not.toBeInTheDocument();
  });

  it('shows upcoming public contests without allowing team creation', () => {
    renderExplore('/contests/upcoming');
    expect(screen.getByText('접수 예정')).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '팀 만들기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('접수가 시작되면 팀을 만들거나 지원할 수 있어요.'),
    ).toBeInTheDocument();
  });
});
