import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import {
  LoginPage,
  ProfilePage,
  PublicProfilePage,
  SignupPage,
  ProfileVisibilityControl,
} from './AccountPages';
import { demoId, demoPassword } from './auth-policy';
import { weeklyAvailabilityOptions } from './profile-fields';
import { CreateTeamPage } from './CreateTeamPage';
import { getPublicProfile, initialProfile, initialTeams } from './data';
import { PreviewProvider } from './PreviewProvider';
import { PreviewContext, type PreviewState } from './preview-context';

function CurrentLocation() {
  const location = useLocation();
  return (
    <p>
      이동한 경로: {location.pathname}
      {location.search}
    </p>
  );
}

function renderAccount(path: string, overrides: Partial<PreviewState> = {}) {
  const state: PreviewState = {
    signedIn: true,
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
    createTeam: vi.fn(() => 'new-team'),
    reset: vi.fn(),
    emptyWorkspace: vi.fn(),
    ...overrides,
  };
  render(
    <MemoryRouter initialEntries={[path]}>
      <PreviewContext value={state}>
        <Routes>
          <Route path="/design-preview/login" element={<LoginPage />} />
          <Route path="/design-preview/signup" element={<SignupPage />} />
          <Route path="/design-preview/profile" element={<ProfilePage />} />
          <Route
            path="/design-preview/teams/new"
            element={<CreateTeamPage />}
          />
          <Route path="*" element={<CurrentLocation />} />
        </Routes>
      </PreviewContext>
    </MemoryRouter>,
  );
  return state;
}

async function enterLogin(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('아이디', { exact: true }), demoId);
  await user.type(
    screen.getByLabelText('비밀번호', { exact: true }),
    demoPassword,
  );
}

async function renderProfileFlow() {
  render(
    <MemoryRouter
      initialEntries={[
        '/design-preview/login?returnTo=%2Fdesign-preview%2Fprofile',
      ]}
    >
      <PreviewProvider>
        <Routes>
          <Route path="/design-preview/login" element={<LoginPage />} />
          <Route path="/design-preview/profile" element={<ProfilePage />} />
          <Route
            path="/design-preview/profile/public"
            element={<PublicProfilePage />}
          />
        </Routes>
      </PreviewProvider>
    </MemoryRouter>,
  );
  const user = userEvent.setup();
  await enterLogin(user);
  await user.click(screen.getByRole('button', { name: '로그인' }));
  await screen.findByRole('button', { name: '프로필 수정' });
}

describe('design preview account flows', () => {
  it('projects every registered field of a public profile and none of a private profile', () => {
    const profile = {
      ...initialProfile,
      academicStatus: '재학',
      skills: ['프로그래밍'],
      experience: '프로젝트 경험',
      experienceState: 'provided' as const,
      portfolio: 'https://example.com/work',
      portfolioTitle: '작업집',
      visibility: { discoverable: true },
    };
    expect(getPublicProfile(profile)).toMatchObject({
      id: 'me',
      name: profile.name,
      interests: profile.interests,
      intro: profile.intro,
      availability: profile.availability,
      academicStatus: '재학',
      skills: ['프로그래밍'],
      experience: '프로젝트 경험',
      portfolio: profile.portfolio,
      portfolioTitle: '작업집',
    });
    expect(
      getPublicProfile({ ...profile, visibility: { discoverable: false } }),
    ).toBeNull();
  });

  it('keeps character choices in the edit draft until saved and discards cancelled choices', async () => {
    await renderProfileFlow();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    await user.click(
      screen.getByRole('button', { name: '프로필 이미지 변경, 현재 스콘' }),
    );
    let picker = screen.getByRole('dialog', { name: '프로필 이미지 변경' });
    expect(within(picker).getAllByRole('radio')).toHaveLength(5);
    await user.click(within(picker).getByRole('radio', { name: '아티' }));
    await user.click(within(picker).getByRole('button', { name: '취소' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole('button', { name: '프로필 이미지 변경, 현재 스콘' }),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', { name: '프로필 이미지 변경, 현재 스콘' }),
    );
    picker = screen.getByRole('dialog', { name: '프로필 이미지 변경' });
    expect(within(picker).getByRole('radio', { name: '스콘' })).toBeChecked();
    await user.click(within(picker).getByRole('radio', { name: '디모' }));
    await user.click(
      within(picker).getByRole('button', { name: '이 캐릭터로 선택' }),
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole('button', { name: '프로필 이미지 변경, 현재 디모' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '취소' }));
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    expect(
      screen.getByRole('button', { name: '프로필 이미지 변경, 현재 스콘' }),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', { name: '프로필 이미지 변경, 현재 스콘' }),
    );
    picker = screen.getByRole('dialog', { name: '프로필 이미지 변경' });
    await user.click(within(picker).getByRole('radio', { name: '컨버' }));
    await user.click(
      within(picker).getByRole('button', { name: '이 캐릭터로 선택' }),
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await user.click(screen.getByRole('switch', { name: '프로필 공개' }));
    await user.click(screen.getByRole('button', { name: '공개로 전환' }));
    expect(
      screen.getByRole('region', { name: '내 기본 정보' }).querySelector('img'),
    ).toHaveAttribute('src', '/mascots/conver.png');
    await user.click(screen.getByRole('link', { name: '공개된 모습 보기' }));
    expect(
      screen
        .getByRole('heading', { name: initialProfile.name })
        .closest('section')
        ?.querySelector('img'),
    ).toHaveAttribute('src', '/mascots/conver.png');
  });

  it('uses the default character when no optional avatar is selected', () => {
    expect(
      getPublicProfile({
        ...initialProfile,
        avatarId: undefined,
        visibility: { ...initialProfile.visibility, discoverable: true },
      })?.avatarId,
    ).toBe('skon');
  });

  it.each([false, true])(
    'requires confirmation for a visibility change from %s and preserves cancelled changes',
    async (discoverable) => {
      const profile = { ...initialProfile, visibility: { discoverable } };
      const state = renderAccount('/design-preview/profile', { profile });
      const user = userEvent.setup();
      const toggle = screen.getByRole('switch', { name: '프로필 공개' });
      await user.click(toggle);
      expect(toggle).toHaveAttribute('aria-checked', String(discoverable));
      expect(state.saveProfile).not.toHaveBeenCalled();
      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveAccessibleDescription(
        /이미 지원받은 팀장은 전체 현재 프로필을 볼 수 있고, AI 지원자 검토에도 최신 프로필/,
      );
      await user.click(within(dialog).getByRole('button', { name: '취소' }));
      await waitFor(() =>
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
      );
      expect(state.saveProfile).not.toHaveBeenCalled();
      await user.click(toggle);
      await user.keyboard('{Escape}');
      await waitFor(() =>
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
      );
      expect(state.saveProfile).not.toHaveBeenCalled();
      await user.click(toggle);
      await user.click(
        screen.getByRole('button', {
          name: discoverable ? '비공개로 전환' : '공개로 전환',
        }),
      );
      expect(state.saveProfile).toHaveBeenCalledExactlyOnceWith({
        ...profile,
        visibility: { discoverable: !discoverable },
      });
    },
  );

  it('shows all saved fields after public confirmation and hides the entire preview after private confirmation', async () => {
    await renderProfileFlow();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    await user.type(
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https://example.com/work',
    );
    await user.type(
      screen.getByLabelText('포트폴리오 제목 (선택)'),
      '나의 작업',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await user.click(screen.getByRole('switch', { name: '프로필 공개' }));
    await user.click(screen.getByRole('button', { name: '공개로 전환' }));
    await user.click(screen.getByRole('link', { name: '공개된 모습 보기' }));
    expect(screen.getByText(initialProfile.intro)).toBeVisible();
    expect(screen.getByText('미입력')).toBeVisible();
    expect(screen.getByRole('link', { name: /나의 작업/ })).toHaveAttribute(
      'href',
      'https://example.com/work',
    );
    await user.click(screen.getByRole('link', { name: '내 프로필' }));
    await user.click(screen.getByRole('switch', { name: '프로필 공개' }));
    await user.click(screen.getByRole('button', { name: '비공개로 전환' }));
    await user.click(screen.getByRole('link', { name: '공개된 모습 보기' }));
    expect(screen.getByText('현재 비공개 상태입니다.')).toBeVisible();
    expect(screen.queryByText(initialProfile.intro)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /나의 작업/ }),
    ).not.toBeInTheDocument();
  });

  it('explains unavailable school verification in a dismissible popup without changing the profile', async () => {
    const state = renderAccount('/design-preview/profile');
    const user = userEvent.setup();
    await user.click(
      screen.getByRole('button', { name: '교내 미인증, 학교 인증 안내' }),
    );
    const popup = await screen.findByRole('dialog', { name: '학교 인증 안내' });
    expect(popup).toHaveAccessibleDescription(
      /학교 인증은 아직 제공하지 않는 기능이에요/,
    );
    await user.click(within(popup).getByRole('button', { name: '확인' }));
    await waitFor(() => expect(popup).not.toBeInTheDocument());
    expect(
      screen.getByRole('button', { name: '교내 미인증, 학교 인증 안내' }),
    ).toBeInTheDocument();
    expect(state.saveProfile).not.toHaveBeenCalled();
  });

  it('starts with empty fields and reveals a password without submitting or changing it', async () => {
    const state = renderAccount('/design-preview/login');
    const user = userEvent.setup();
    const input = screen.getByLabelText('비밀번호', { exact: true });
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveValue('');
    await enterLogin(user);
    await user.click(screen.getByRole('button', { name: '비밀번호 보기' }));
    expect(input).toHaveAttribute('type', 'text');
    expect(
      screen.getByRole('button', { name: '비밀번호 숨기기' }),
    ).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: '비밀번호 숨기기' }));
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveValue(demoPassword);
    expect(state.signIn).not.toHaveBeenCalled();
  });

  it('reports invalid demo credentials and restores a working demo login', async () => {
    const state = renderAccount(
      '/design-preview/login?from=%2Fdesign-preview%2Fteams%2Fmakers',
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('아이디'), '  DREAMONDEMO  ');
    await user.type(screen.getByLabelText('비밀번호'), 'incorrect-password');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '아이디 또는 비밀번호를 확인',
    );
    expect(state.signIn).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText('비밀번호'));
    await user.type(screen.getByLabelText('비밀번호'), demoPassword);
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(
      await screen.findByText('이동한 경로: /design-preview/teams/makers'),
    ).toBeInTheDocument();
    expect(state.signIn).toHaveBeenCalledOnce();
  });

  it.each([
    'https://example.com',
    '//example.com',
    '/design-preview/../../private',
    '/design-preview-other',
  ])('keeps login return path inside the preview for %s', async (target) => {
    renderAccount(
      `/design-preview/login?returnTo=${encodeURIComponent(target)}`,
    );
    const user = userEvent.setup();
    await enterLogin(user);
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(
      await screen.findByText('이동한 경로: /design-preview/workspace'),
    ).toBeInTheDocument();
  });

  it('preserves the original team destination when visiting signup and returning to login', async () => {
    const state = renderAccount(
      '/design-preview/login?returnTo=%2Fdesign-preview%2Fteams%2Fmakers',
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('link', { name: '회원가입' }));
    await user.click(screen.getByRole('link', { name: '로그인으로' }));
    await enterLogin(user);
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(
      await screen.findByText('이동한 경로: /design-preview/teams/makers'),
    ).toBeInTheDocument();
    expect(state.signIn).toHaveBeenCalledOnce();
  });

  it('validates profile requirements and saves an optional portfolio without changing global privacy', async () => {
    const state = renderAccount('/design-preview/profile', {
      profile: { ...initialProfile, availability: '' },
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    await user.clear(screen.getByLabelText('이름 (필수)'));
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      await screen.findByText('이름을 입력해 주세요.'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('이름 (필수)')).toHaveAttribute(
      'aria-invalid',
      'true',
    );
    expect(state.saveProfile).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('이름 (필수)'), '김예시');
    await user.type(
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'javascript:alert(1)',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      await screen.findByText(
        'http:// 또는 https://로 시작하는 링크를 입력해 주세요.',
      ),
    ).toBeInTheDocument();
    await user.clear(screen.getByLabelText('포트폴리오 링크 (선택)'));
    await user.type(
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https://example.com/portfolio',
    );
    await user.selectOptions(
      screen.getByLabelText('주당 참여 가능 시간 (선택)'),
      '5~10시간 미만',
    );
    expect(state.saveProfile).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      '프로필을 저장했어요.',
    );
    expect(state.saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '김예시',
        portfolio: 'https://example.com/portfolio',

        availability: '5~10시간 미만',
      }),
    );
  });

  it('keeps weekly availability optional and discards unsaved changes', async () => {
    const state = renderAccount('/design-preview/profile', {
      profile: { ...initialProfile, availability: '10~20시간 미만' },
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    const field = screen.getByLabelText('주당 참여 가능 시간 (선택)');
    expect(
      within(field)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['미입력', ...weeklyAvailabilityOptions]);
    expect(field).toHaveAccessibleDescription(/참여 중인 모든 프로젝트를 합한/);
    await user.selectOptions(field, '20시간 이상');
    await user.click(screen.getByRole('button', { name: '취소' }));
    expect(state.saveProfile).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    expect(screen.getByLabelText('주당 참여 가능 시간 (선택)')).toHaveValue(
      '10~20시간 미만',
    );
    await user.selectOptions(
      screen.getByLabelText('주당 참여 가능 시간 (선택)'),
      '',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(state.saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({ availability: '' }),
    );
  });

  it('retains portfolio edits only after saving and preserves the global privacy state', async () => {
    await renderProfileFlow();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    await user.type(
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https://example.com/draft',
    );
    await user.click(screen.getByRole('button', { name: '취소' }));
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    expect(screen.getByLabelText('포트폴리오 링크 (선택)')).toHaveValue('');
    await user.type(
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https://example.com/saved',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      screen.getByRole('switch', { name: '프로필 공개' }),
    ).not.toBeChecked();
    expect(
      screen.getByRole('link', { name: /등록한 링크 열기/ }),
    ).toHaveAttribute('href', 'https://example.com/saved');
  });

  it('rejects unsafe portfolio URLs without saving profile changes', async () => {
    const state = renderAccount('/design-preview/profile?edit=details');
    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'javascript:alert(1)',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      screen.getByText(
        'http:// 또는 https://로 시작하는 링크를 입력해 주세요.',
      ),
    ).toBeVisible();
    expect(state.saveProfile).not.toHaveBeenCalled();
  });

  it('clears the portfolio title when its URL is deleted', async () => {
    const state = renderAccount('/design-preview/profile', {
      profile: {
        ...initialProfile,
        portfolio: 'https://example.com/previous',
      },
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    await user.clear(screen.getByLabelText('포트폴리오 링크 (선택)'));
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(state.saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({ portfolio: '', portfolioTitle: '' }),
    );
  });

  it('requires at least one profile role and permits cancellation without saving', async () => {
    const state = renderAccount('/design-preview/profile');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    const roles = screen.getByRole('group', { name: /희망 역할/ });
    for (const selected of within(roles).getAllByRole('checkbox', {
      checked: true,
    }))
      await user.click(selected);
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      await screen.findByText('희망 역할을 하나 이상 선택해 주세요.'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '취소' }));
    expect(
      screen.getByRole('button', { name: '프로필 수정' }),
    ).toBeInTheDocument();
    expect(state.saveProfile).not.toHaveBeenCalled();
  });

  it('completes signup preview without automatic sign-in or passing credentials into profile state', async () => {
    const state = renderAccount('/design-preview/signup');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('아이디 (필수)'), '  NewAccount  ');
    await user.type(screen.getByLabelText('비밀번호 (필수)'), 'abcdefg!');
    await user.type(screen.getByLabelText('이름 (필수)'), '김지우');
    await user.click(
      within(screen.getByRole('group', { name: /관심 분야/ })).getByLabelText(
        '교육',
      ),
    );
    await user.click(
      within(screen.getByRole('group', { name: /희망 역할/ })).getByLabelText(
        '기획',
      ),
    );
    await user.click(screen.getByRole('button', { name: '회원가입' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      '서경드림온에 오신 것을 환영해요.',
    );
    expect(state.signIn).not.toHaveBeenCalled();
    expect(state.signOut).toHaveBeenCalledOnce();
    expect(state.saveProfile).toHaveBeenCalledOnce();
    const saved = vi.mocked(state.saveProfile).mock.calls[0]?.[0];
    expect(saved).not.toHaveProperty('password');
    expect(saved).not.toHaveProperty('username');
    expect(screen.queryByLabelText('비밀번호 (필수)')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인' })).toHaveAttribute(
      'href',
      '/design-preview/login?returnTo=%2Fdesign-preview%2Fprofile',
    );
  });

  it('keeps signed-out team creation behind login and preserves the contest choice', () => {
    const state = renderAccount('/design-preview/teams/new?contest=campus', {
      signedIn: false,
    });
    expect(screen.queryByLabelText('팀 이름')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인하기' })).toHaveAttribute(
      'href',
      '/design-preview/login?returnTo=%2Fdesign-preview%2Fteams%2Fnew%3Fcontest%3Dcampus',
    );
    expect(state.createTeam).not.toHaveBeenCalled();
  });

  it('validates team fields, creates the chosen contest team and navigates to its own detail', async () => {
    const state = renderAccount('/design-preview/teams/new?contest=green', {
      teams: [],
    });
    const user = userEvent.setup();
    expect(screen.getByLabelText('참여 공모전')).toHaveTextContent(
      '일상 속 그린테크 챌린지',
    );
    await user.click(screen.getByRole('button', { name: '팀 만들기' }));
    expect(
      await screen.findByText('팀 이름을 2자 이상 입력해 주세요.'),
    ).toBeInTheDocument();
    expect(state.createTeam).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('팀 이름'), '새로운 예시 팀');
    await user.type(
      screen.getByLabelText('팀 소개와 목표'),
      '환경 문제를 함께 해결해요.',
    );
    await user.type(screen.getByLabelText('팀장 포함 총 정원'), '3');
    await user.click(
      within(screen.getByRole('group', { name: /모집할 역할/ })).getByLabelText(
        '개발',
      ),
    );
    await user.type(screen.getByLabelText('팀 모집 마감'), '2026-10-24');
    await user.click(screen.getByRole('button', { name: '팀 만들기' }));
    expect(
      await screen.findByText(
        '이동한 경로: /design-preview/teams/new-team?view=space',
      ),
    ).toBeInTheDocument();
    expect(state.createTeam).toHaveBeenCalledWith({
      contestId: 'green',
      name: '새로운 예시 팀',
      summary: '환경 문제를 함께 해결해요.',
      roles: ['개발'],
      capacity: 3,
      recruitmentDeadline: '2026-10-24',
      interests: ['환경', 'IT·기술'],
    });
  });

  it('requires a known contest and preserves the team draft while searching and changing it', async () => {
    const state = renderAccount('/design-preview/teams/new?contest=unknown', {
      teams: [],
    });
    const user = userEvent.setup();
    const trigger = screen.getByLabelText('참여 공모전');
    await user.type(screen.getByLabelText('팀 이름'), '검색해서 만든 팀');
    await user.type(
      screen.getByLabelText('팀 소개와 목표'),
      '함께 자료를 조사하고 정리해요.',
    );
    await user.click(screen.getByRole('button', { name: '팀 만들기' }));
    expect(
      await screen.findByText('참여할 공모전을 선택해 주세요.'),
    ).toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-invalid', 'true');
    expect(trigger).toHaveAccessibleDescription(
      /참여할 공모전을 선택해 주세요/,
    );
    await user.click(trigger);
    const drawer = await screen.findByRole('dialog', { name: '공모전 선택' });
    await user.type(
      within(drawer).getByRole('combobox', { name: '공모전 검색' }),
      '로컬',
    );
    await user.click(
      within(drawer).getByRole('option', {
        name: /우리 동네를 새롭게, 로컬 브랜딩/,
      }),
    );
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    expect(state.createTeam).not.toHaveBeenCalled();
    expect(trigger).toHaveTextContent('우리 동네를 새롭게, 로컬 브랜딩');
    expect(screen.getByLabelText('팀 이름')).toHaveValue('검색해서 만든 팀');
    expect(screen.getByLabelText('팀 소개와 목표')).toHaveValue(
      '함께 자료를 조사하고 정리해요.',
    );
    await user.type(screen.getByLabelText('팀장 포함 총 정원'), '3');
    await user.click(
      within(screen.getByRole('group', { name: /모집할 역할/ })).getByLabelText(
        '개발',
      ),
    );
    await user.type(screen.getByLabelText('팀 모집 마감'), '2026-11-01');
    await user.click(screen.getByRole('button', { name: '팀 만들기' }));
    await waitFor(() =>
      expect(state.createTeam).toHaveBeenCalledWith({
        contestId: 'local',
        name: '검색해서 만든 팀',
        summary: '함께 자료를 조사하고 정리해요.',
        roles: ['개발'],
        capacity: 3,
        recruitmentDeadline: '2026-11-01',
        interests: ['디자인', '사회·문화'],
      }),
    );
  });

  it('keeps the global privacy state when saving profile details without field-level toggles', async () => {
    const state = renderAccount('/design-preview/profile?edit=details');
    const user = userEvent.setup();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(state.saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({ visibility: { discoverable: false } }),
    );
  });

  it('clears dependent selections when the college changes, and skips majors for an independent department', async () => {
    const state = renderAccount('/design-preview/profile?edit=details');
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByLabelText('단과대학 (선택)'),
      '미래융합대학',
    );
    await user.selectOptions(
      screen.getByLabelText('학부·학과 (선택)'),
      '자유전공학부',
    );
    await user.selectOptions(
      screen.getByLabelText('세부전공 (선택)'),
      '전공 미배정',
    );
    await user.selectOptions(
      screen.getByLabelText('단과대학 (선택)'),
      '이공대학',
    );
    expect(screen.getByLabelText('학부·학과 (선택)')).toHaveValue('');
    expect(screen.queryByLabelText('세부전공 (선택)')).not.toBeInTheDocument();
    expect(
      within(screen.getByLabelText('학부·학과 (선택)')).queryByRole('option', {
        name: '자유전공학부',
      }),
    ).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText('학부·학과 (선택)'),
      '소프트웨어학과',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(state.saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({
        college: '이공대학',
        department: '소프트웨어학과',
        major: '',
      }),
    );
  });

  it('preserves a stored legacy affiliation while other profile fields change', async () => {
    const state = renderAccount('/design-preview/profile?edit=details', {
      profile: {
        ...initialProfile,
        college: '과거 대학',
        department: '과거 학부',
        major: '과거 전공',
      },
    });
    const user = userEvent.setup();
    expect(
      screen.getByRole('option', { name: '과거 대학 (기존 소속)' }),
    ).toBeDisabled();
    await user.type(screen.getByLabelText('자기소개 (선택)'), ' 새로운 소개');
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(state.saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({
        college: '과거 대학',
        department: '과거 학부',
        major: '과거 전공',
      }),
    );
  });

  it('distinguishes no experience, removes other choices and saves optional skills and portfolio title', async () => {
    const state = renderAccount('/design-preview/profile?edit=details');
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByLabelText('경험 등록 상태 (선택)'),
      'none',
    );
    expect(screen.getByLabelText('관련 경험 (선택)')).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: '프로그래밍' }));
    const skills = screen.getByRole('group', { name: /보유 역량/ });
    expect(
      within(skills).queryByRole('checkbox', { name: '기타' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText('기타 역량 설명 (선택)'),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByLabelText('학적 상태 (선택)')).queryByRole('option', {
        name: '기타',
      }),
    ).not.toBeInTheDocument();
    await user.type(
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https://example.com/work',
    );
    await user.type(
      screen.getByLabelText('포트폴리오 제목 (선택)'),
      '나의 작업',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(state.saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({
        experienceState: 'none',
        experience: '',
        skills: ['프로그래밍'],
        portfolioTitle: '나의 작업',
      }),
    );
  });

  it('returns to the team after required profile completion without submitting an application', async () => {
    const state = renderAccount(
      '/design-preview/profile?edit=details&returnTo=%2Fdesign-preview%2Fteams%2Fmakers',
      { profile: { ...initialProfile, name: '' } },
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('이름 (필수)'), '김지우');
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      screen.getByText('이동한 경로: /design-preview/teams/makers'),
    ).toBeInTheDocument();
    expect(state.apply).not.toHaveBeenCalled();
  });
  it.each([
    ['이름 (필수)', 50, '이름은 50자 이내로 입력해 주세요.'],
    ['자기소개 (선택)', 300, '자기소개는 300자 이내로 입력해 주세요.'],
    ['관련 경험 (선택)', 500, '관련 경험은 500자 이내로 입력해 주세요.'],
    [
      '포트폴리오 제목 (선택)',
      50,
      '포트폴리오 제목은 50자 이내로 입력해 주세요.',
    ],
  ])(
    'preserves over-limit %s text and explains the error instead of truncating',
    async (label, max, message) => {
      const state = renderAccount('/design-preview/profile?edit=details');
      const user = userEvent.setup();
      const field = screen.getByLabelText(label);
      const oversized = '가'.repeat(max + 1);
      fireEvent.change(field, { target: { value: oversized } });
      await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
      expect(await screen.findByText(message)).toBeVisible();
      expect(field).toHaveValue(oversized);
      expect(field).toHaveAttribute('aria-invalid', 'true');
      expect(state.saveProfile).not.toHaveBeenCalled();
    },
  );

  it('validates profile selection maximums and keeps all invalid choices for correction', async () => {
    const state = renderAccount('/design-preview/profile?edit=details');
    const user = userEvent.setup();
    const roles = screen.getByRole('group', { name: /희망 역할/ });
    await user.click(within(roles).getByLabelText('개발'));
    await user.click(within(roles).getByLabelText('발표'));
    const interests = screen.getByRole('group', { name: /관심 분야/ });
    await user.click(within(interests).getByLabelText('환경'));
    await user.click(within(interests).getByLabelText('디자인'));
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      await screen.findByText('희망 역할은 최대 2개까지 선택해 주세요.'),
    ).toBeVisible();
    expect(
      screen.getByText('관심 분야는 최대 3개까지 선택해 주세요.'),
    ).toBeVisible();
    expect(
      within(roles).getAllByRole('checkbox', { checked: true }),
    ).toHaveLength(3);
    expect(
      within(interests).getAllByRole('checkbox', { checked: true }),
    ).toHaveLength(4);
    expect(state.saveProfile).not.toHaveBeenCalled();
    await user.click(within(roles).getByLabelText('발표'));
    await user.click(within(interests).getByLabelText('디자인'));
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(state.saveProfile).toHaveBeenCalledOnce();
  });

  it('treats blank experience as unspecified, trims saved text and permits omitted academics', async () => {
    const state = renderAccount('/design-preview/profile?edit=details', {
      profile: {
        ...initialProfile,
        experienceState: 'provided',
        experience: '이전 경험',
      },
    });
    const user = userEvent.setup();
    fireEvent.change(screen.getByLabelText('이름 (필수)'), {
      target: { value: '  김지우  ' },
    });
    fireEvent.change(screen.getByLabelText('관련 경험 (선택)'), {
      target: { value: '   ' },
    });
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(state.saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '김지우',
        experience: '',
        experienceState: 'unspecified',
        academicStatus: '',
        grade: '',
      }),
    );
  });

  it('preserves valid academic descendants when the same parent relationship is selected', async () => {
    const state = renderAccount('/design-preview/profile?edit=details', {
      profile: {
        ...initialProfile,
        college: '인문사회과학대학',
        department: '경영학부',
        major: '경영학전공',
      },
    });
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByLabelText('단과대학 (선택)'),
      '인문사회과학대학',
    );
    await user.selectOptions(
      screen.getByLabelText('학부·학과 (선택)'),
      '경영학부',
    );
    expect(screen.getByLabelText('세부전공 (선택)')).toHaveValue('경영학전공');
    await user.selectOptions(
      screen.getByLabelText('학부·학과 (선택)'),
      '공공인재학부',
    );
    expect(screen.getByLabelText('세부전공 (선택)')).toHaveValue('');
    await user.click(screen.getByRole('button', { name: '취소' }));
    expect(state.saveProfile).not.toHaveBeenCalled();
  });

  it('supports the application visibility button and keeps a failed save open for retry', async () => {
    const onConfirm = vi
      .fn()
      .mockRejectedValueOnce(new Error('save failed'))
      .mockResolvedValueOnce(undefined);
    render(
      <ProfileVisibilityControl
        checked={false}
        onConfirm={onConfirm}
        triggerLabel="프로필 공개하기"
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '프로필 공개하기' }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAccessibleDescription(
      /공개 전환만으로 지원이 접수되지는 않아요/,
    );
    await user.click(
      within(dialog).getByRole('button', { name: '공개로 전환' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '공개 설정을 저장하지 못했어요',
    );
    expect(dialog).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole('button', { name: '공개로 전환' }),
    );
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(onConfirm).toHaveBeenNthCalledWith(1, true);
    expect(onConfirm).toHaveBeenNthCalledWith(2, true);
  });
  it('reports forbidden signup characters immediately without changing the input', async () => {
    renderAccount('/design-preview/signup');
    const user = userEvent.setup();
    const password = screen.getByLabelText('비밀번호 (필수)');
    await user.click(password);
    for (const value of ['한abcdef!', 'abc def!', 'abcdefg! ']) {
      await user.clear(password);
      await user.paste(value);
      expect(
        await screen.findByText('한글과 공백은 사용할 수 없어요.'),
      ).toBeVisible();
      expect(password).toHaveValue(value);
      expect(password).toHaveFocus();
      expect(password).toHaveAttribute('aria-invalid', 'true');
    }
    await user.clear(password);
    await user.paste('abcdefg!');
    await waitFor(() =>
      expect(
        screen.queryByText('한글과 공백은 사용할 수 없어요.'),
      ).not.toBeInTheDocument(),
    );
    expect(password).toHaveAttribute('aria-invalid', 'false');
  });

  it('announces Caps Lock while entering a signup password and clears it on key release or blur', async () => {
    renderAccount('/design-preview/signup');
    const user = userEvent.setup();
    const password = screen.getByLabelText('비밀번호 (필수)');
    await user.click(password);
    expect(
      screen.queryByText('Caps Lock이 켜져 있어요.'),
    ).not.toBeInTheDocument();
    fireEvent.keyUp(password, { key: 'CapsLock', modifierCapsLock: true });
    expect(screen.getByText('Caps Lock이 켜져 있어요.')).toBeVisible();
    expect(password).toHaveAttribute(
      'aria-describedby',
      expect.stringContaining('signup-password-caps-lock'),
    );
    fireEvent.keyDown(password, { key: 'a', modifierCapsLock: false });
    expect(
      screen.queryByText('Caps Lock이 켜져 있어요.'),
    ).not.toBeInTheDocument();
    fireEvent.keyDown(password, { key: 'A', modifierCapsLock: true });
    expect(screen.getByText('Caps Lock이 켜져 있어요.')).toBeVisible();
    fireEvent.blur(password);
    expect(
      screen.queryByText('Caps Lock이 켜져 있어요.'),
    ).not.toBeInTheDocument();
    fireEvent.keyUp(password, { key: 'A', modifierCapsLock: true });
    expect(screen.getByText('Caps Lock이 켜져 있어요.')).toBeVisible();
    fireEvent.blur(window);
    expect(
      screen.queryByText('Caps Lock이 켜져 있어요.'),
    ).not.toBeInTheDocument();
  });

  it('normalizes duplicate signup IDs and preserves pasted over-limit passwords for correction', async () => {
    const state = renderAccount('/design-preview/signup');
    const user = userEvent.setup();
    const username = screen.getByLabelText('아이디 (필수)');
    await user.click(username);
    await user.paste('  DREAMONDEMO  ');
    expect(await screen.findByText('이미 사용 중인 아이디예요.')).toBeVisible();
    const password = screen.getByLabelText('비밀번호 (필수)');
    const oversized = 'a'.repeat(128) + '!';
    await user.click(password);
    await user.paste(oversized);
    await user.tab();
    expect(
      await screen.findByText('비밀번호는 128자 이하로 입력해 주세요.'),
    ).toBeVisible();
    expect(password).toHaveValue(oversized);
    expect(screen.getByText('8자 이상').closest('li')).toHaveAttribute(
      'data-met',
      'true',
    );
    expect(password).toHaveAttribute('autocomplete', 'new-password');
    await user.click(screen.getByRole('button', { name: '비밀번호 보기' }));
    expect(password).toHaveAttribute('type', 'text');
    expect(password).toHaveValue(oversized);
    await user.click(screen.getByRole('button', { name: '비밀번호 숨기기' }));
    expect(password).toHaveAttribute('type', 'password');
    await user.clear(password);
    await user.paste('password!');
    expect(
      await screen.findByText(
        '쉽게 추측할 수 있는 비밀번호예요. 다른 비밀번호를 선택해 주세요.',
      ),
    ).toBeVisible();
    expect(state.saveProfile).not.toHaveBeenCalled();
  });
});
