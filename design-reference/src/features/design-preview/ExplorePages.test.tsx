import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { ContestPage, ExplorePage, PersonPage } from './ExplorePages';
import {
  archivedContest,
  contests,
  initialProfile,
  initialTeams,
  people,
} from './data';
import { PreviewContext, type PreviewState } from './preview-context';

function renderExplore(path: string, overrides: Partial<PreviewState> = {}) {
  const state: PreviewState = {
    signedIn: false,
    profile: initialProfile,
    teams: initialTeams,
    applications: [],
    applicants: [],
    signIn: vi.fn(),
    signOut: vi.fn(),
    saveProfile: vi.fn(),
    apply: vi.fn(() => true),
    selectApplicant: vi.fn(() => true),
    cancelApplication: vi.fn(() => true),
    closeRecruitment: vi.fn(() => true),
    createTeam: vi.fn(() => 'created'),
    reset: vi.fn(),
    emptyWorkspace: vi.fn(),
    ...overrides,
  };
  render(
    <MemoryRouter initialEntries={[path]}>
      <PreviewContext value={state}>
        <Routes>
          <Route path="/design-preview/explore" element={<ExplorePage />} />
          <Route
            path="/design-preview/people/:personId"
            element={<PersonPage />}
          />
          <Route
            path="/design-preview/contests/:contestId"
            element={<ContestPage />}
          />
        </Routes>
      </PreviewContext>
    </MemoryRouter>,
  );
  return state;
}

describe('official reference public exploration', () => {
  it('allows guests to read and filter public contests using the shared interests', async () => {
    renderExplore('/design-preview/explore');
    expect(
      screen.getByRole('heading', { name: contests[0]!.title }),
    ).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '탐색 필터' }));
    await user.click(screen.getByRole('radio', { name: '교육' }));
    await user.click(screen.getByRole('button', { name: '필터 적용' }));
    expect(screen.getByRole('status')).toHaveTextContent('검색 결과 1개');
    expect(
      screen.getByRole('heading', { name: contests[0]!.title }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: contests[1]!.title }),
    ).not.toBeInTheDocument();
  });

  it('discards filter drafts and clears applied filters while retaining the selected tab', async () => {
    renderExplore('/design-preview/explore?tab=teams&role=개발&open=true');
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
    renderExplore('/design-preview/explore?sort=deadline');
    expect(
      screen.getByRole('link', { name: 'AI에게 추천 받기' }),
    ).toHaveAttribute('href', '/design-preview/ai');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '검색 조건 초기화' }));
    expect(screen.getByLabelText('정렬')).toHaveValue('default');
    expect(
      screen.queryByRole('button', { name: '검색 조건 초기화' }),
    ).not.toBeInTheDocument();
  });

  it('keeps public team recruitment visible to guests without exposing team space', () => {
    const state = renderExplore('/design-preview/explore?tab=teams');
    const link = screen.getByRole('link', { name: /캠퍼스 메이커스/ });
    expect(link).toHaveAttribute(
      'href',
      '/design-preview/teams/makers?from=%2Fdesign-preview%2Fexplore%3Ftab%3Dteams',
    );
    expect(
      screen.queryByRole('link', { name: /팀 공간/ }),
    ).not.toBeInTheDocument();
    expect(state.apply).not.toHaveBeenCalled();
  });

  it('does not expose people or their search matches to guests', () => {
    renderExplore('/design-preview/explore?tab=people&q=정수아');
    expect(
      screen.getByRole('heading', {
        name: '로그인하고 함께할 사람을 찾아보세요',
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('검색 결과 0개');
    for (const person of people)
      expect(
        screen.queryByRole('heading', { name: person.name }),
      ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인하기' })).toHaveAttribute(
      'href',
      '/design-preview/login?returnTo=%2Fdesign-preview%2Fexplore%3Ftab%3Dpeople',
    );
  });

  it('guards direct people detail links and keeps the target for login', () => {
    renderExplore('/design-preview/people/sua');
    expect(
      screen.getByRole('heading', { name: '로그인이 필요해요' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('정수아')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '희망 역할' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인하기' })).toHaveAttribute(
      'href',
      '/design-preview/login?returnTo=%2Fdesign-preview%2Fpeople%2Fsua',
    );
  });

  it('does not create a public detail for a profile excluded from people exploration', () => {
    renderExplore('/design-preview/people/me', { signedIn: true });
    expect(
      screen.getByRole('heading', { name: '프로필을 찾을 수 없어요' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(initialProfile.name)).not.toBeInTheDocument();
  });

  it('does not search hidden profile fields even when the profile is listed', () => {
    renderExplore('/design-preview/explore?tab=people&q=비공개프로젝트', {
      signedIn: true,
      profile: {
        ...initialProfile,
        experience: '비공개프로젝트',
        experienceState: 'provided',
        visibility: {
          discoverable: true,
          interests: false,
          experience: false,
          intro: false,
        },
      },
    });
    expect(
      screen.getByRole('heading', { name: '검색 결과가 없어요' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: initialProfile.name }),
    ).not.toBeInTheDocument();
  });

  it('projects only permitted fields and never reveals portfolio consent or personal schedules in a public detail', () => {
    renderExplore('/design-preview/people/me', {
      signedIn: true,
      profile: {
        ...initialProfile,
        intro: '공개된 자기소개',
        experience: '비공개프로젝트',
        portfolio: 'https://example.com/private',
        portfolioTitle: '비공개 작업집',
        portfolioConsent: true,
        visibility: {
          discoverable: true,
          interests: false,
          experience: false,
          intro: true,
        },
      },
    });
    expect(
      screen.getByRole('heading', { name: initialProfile.name }),
    ).toBeInTheDocument();
    expect(screen.getByText('공개된 자기소개')).toBeInTheDocument();
    expect(screen.queryByText('비공개프로젝트')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '관심 분야' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(initialProfile.availability),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('비공개 작업집')).not.toBeInTheDocument();
    expect(
      document.querySelector('a[href="https://example.com/private"]'),
    ).toBeNull();
  });

  it('keeps closed contest history readable with its source while preventing new participation actions', () => {
    const state = renderExplore('/design-preview/contests/archive');
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
    renderExplore('/design-preview/contests/campus');
    const facts = screen.getByText('공식 팀 인원').closest('dl')!;
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
      '/design-preview/teams/new?contest=campus',
    );
  });

  it('makes individual-contest collaboration a preparation group and marks missing submission information', () => {
    renderExplore('/design-preview/contests/local');
    expect(screen.getByText('개인 참가')).toBeInTheDocument();
    expect(
      screen.getByText(
        '개인 참가 공모전이에요. 준비 모임에서 함께 준비하고 접수는 각자 진행해요.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('공식 팀 인원')).not.toBeInTheDocument();
    expect(screen.getByText('공식 공고 확인 필요')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '준비 모임 만들기' }),
    ).toHaveAttribute('href', '/design-preview/teams/new?contest=local');
    expect(
      screen.queryByRole('link', { name: '팀 만들기' }),
    ).not.toBeInTheDocument();
  });
});
