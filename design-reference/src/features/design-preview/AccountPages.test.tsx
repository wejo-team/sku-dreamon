import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import {
  LoginPage,
  ProfilePage,
  PublicProfilePage,
  SignupPage,
} from './AccountPages';
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
    signIn: vi.fn(),
    signOut: vi.fn(),
    saveProfile: vi.fn(),
    apply: vi.fn(() => true),
    selectApplicant: vi.fn(() => true),
    cancelApplication: vi.fn(() => true),
    closeRecruitment: vi.fn(() => true),
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
  await user.type(
    screen.getByLabelText('아이디', { exact: true }),
    'dreamon-demo',
  );
  await user.type(
    screen.getByLabelText('비밀번호', { exact: true }),
    'dreamon-demo',
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
        /지원한 팀장에게는 공개 여부와 관계없이 전체 프로필/,
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
    expect(screen.getByText(initialProfile.availability)).toBeVisible();
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
    expect(input).toHaveValue('dreamon-demo');
    expect(state.signIn).not.toHaveBeenCalled();
  });

  it('reports invalid demo credentials and restores a working demo login', async () => {
    const state = renderAccount(
      '/design-preview/login?from=%2Fdesign-preview%2Fteams%2Fmakers',
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('아이디'), 'dreamon-demo');
    await user.type(screen.getByLabelText('비밀번호'), 'incorrect');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '아이디 또는 비밀번호를 확인',
    );
    expect(state.signIn).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText('비밀번호'));
    await user.type(screen.getByLabelText('비밀번호'), 'dreamon-demo');
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
    await user.click(screen.getByRole('button', { name: '활동 시간 설정' }));
    const availabilityDrawer = await screen.findByRole('dialog', {
      name: '활동 가능 시간',
    });
    await user.click(
      within(availabilityDrawer).getByLabelText('월요일 18:00~21:00'),
    );
    await user.selectOptions(
      within(availabilityDrawer).getByLabelText('요일'),
      '화',
    );
    await user.click(
      within(availabilityDrawer).getByLabelText('화요일 09:00~12:00'),
    );
    await user.click(
      within(availabilityDrawer).getByRole('button', { name: '선택 적용' }),
    );
    await waitFor(() => expect(availabilityDrawer).not.toBeInTheDocument());
    expect(state.saveProfile).not.toHaveBeenCalled();
    expect(
      screen.getByText('월 18:00~21:00; 화 09:00~12:00'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      '프로필을 저장했어요.',
    );
    expect(state.saveProfile).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '김예시',
        portfolio: 'https://example.com/portfolio',

        availability: '월 18:00~21:00; 화 09:00~12:00',
      }),
    );
  });

  it.each(['취소', 'Escape'])(
    'discards unsaved time selections on %s and restores the trigger focus and previous times',
    async (dismissMethod) => {
      const state = renderAccount('/design-preview/profile');
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: '프로필 수정' }));
      const trigger = screen.getByRole('button', { name: '활동 시간 설정' });
      expect(
        screen.queryByLabelText('월요일 18:00~21:00'),
      ).not.toBeInTheDocument();
      await user.click(trigger);
      const drawer = await screen.findByRole('dialog', {
        name: '활동 가능 시간',
      });
      expect(drawer).toHaveAccessibleDescription(
        /공개 프로필과 지원한 팀의 팀장에게 표시돼요/,
      );
      await waitFor(() =>
        expect(within(drawer).getByLabelText('요일')).toHaveFocus(),
      );
      expect(within(drawer).getByLabelText('월요일 18:00~21:00')).toBeChecked();
      await user.click(
        within(drawer).getByRole('button', { name: '시간 선택 지우기' }),
      );
      await user.selectOptions(within(drawer).getByLabelText('요일'), '화');
      await user.click(within(drawer).getByLabelText('화요일 09:00~12:00'));
      if (dismissMethod === '취소') {
        await user.click(within(drawer).getByRole('button', { name: '취소' }));
      } else {
        await user.keyboard('{Escape}');
      }
      await waitFor(() => expect(drawer).not.toBeInTheDocument());
      await waitFor(() => expect(trigger).toHaveFocus());
      expect(screen.getByText(initialProfile.availability)).toBeInTheDocument();
      expect(state.saveProfile).not.toHaveBeenCalled();
      await user.click(trigger);
      const reopened = await screen.findByRole('dialog', {
        name: '활동 가능 시간',
      });
      expect(
        within(reopened).getByLabelText('월요일 18:00~21:00'),
      ).toBeChecked();
      await user.selectOptions(within(reopened).getByLabelText('요일'), '화');
      expect(
        within(reopened).getByLabelText('화요일 09:00~12:00'),
      ).not.toBeChecked();
      await user.selectOptions(within(reopened).getByLabelText('요일'), '목');
      expect(
        within(reopened).getByLabelText('목요일 18:00~21:00'),
      ).toBeChecked();
      await user.keyboard('{Escape}');
      await waitFor(() => expect(reopened).not.toBeInTheDocument());
      await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
      expect(state.saveProfile).toHaveBeenCalledWith(
        expect.objectContaining({ availability: initialProfile.availability }),
      );
    },
  );

  it('applies cleared time selections to the form and saves them only with the profile', async () => {
    const state = renderAccount('/design-preview/profile');
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    const trigger = screen.getByRole('button', { name: '활동 시간 설정' });
    await user.click(trigger);
    const drawer = await screen.findByRole('dialog', {
      name: '활동 가능 시간',
    });
    await user.click(
      within(drawer).getByRole('button', { name: '시간 선택 지우기' }),
    );
    expect(within(drawer).getByText('선택한 시간: 미설정')).toBeInTheDocument();
    await user.click(within(drawer).getByRole('button', { name: '선택 적용' }));
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(screen.getByText('미설정')).toBeInTheDocument();
    expect(state.saveProfile).not.toHaveBeenCalled();
    await user.click(trigger);
    const reopened = await screen.findByRole('dialog', {
      name: '활동 가능 시간',
    });
    expect(
      within(reopened).queryAllByRole('checkbox', { checked: true }),
    ).toHaveLength(0);
    await user.selectOptions(within(reopened).getByLabelText('요일'), '목');
    expect(
      within(reopened).queryAllByRole('checkbox', { checked: true }),
    ).toHaveLength(0);
    await user.keyboard('{Escape}');
    await waitFor(() => expect(reopened).not.toBeInTheDocument());
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
    await user.type(screen.getByLabelText('아이디 (필수)'), 'new-account');
    await user.type(screen.getByLabelText('비밀번호 (필수)'), 'dreamon-demo');
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
      capacity: 4,
      recruitmentDeadline: '2026-10-24',
      interests: [],
      kind: 'entry',
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
    await user.click(
      within(screen.getByRole('group', { name: /모집할 역할/ })).getByLabelText(
        '개발',
      ),
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
    await user.type(screen.getByLabelText('팀 모집 마감'), '2026-11-01');
    await user.click(screen.getByRole('button', { name: '팀 만들기' }));
    await waitFor(() =>
      expect(state.createTeam).toHaveBeenCalledWith({
        contestId: 'local',
        name: '검색해서 만든 팀',
        summary: '함께 자료를 조사하고 정리해요.',
        roles: ['개발'],
        capacity: 4,
        recruitmentDeadline: '2026-11-01',
        interests: [],
        kind: 'preparation',
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

  it('distinguishes no experience and saves optional skill details and portfolio title', async () => {
    const state = renderAccount('/design-preview/profile?edit=details');
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByLabelText('경험 등록 상태 (선택)'),
      'none',
    );
    expect(screen.getByLabelText('관련 경험 (선택)')).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: '프로그래밍' }));
    const skills = screen.getByRole('group', { name: /보유 역량/ });
    await user.click(within(skills).getByRole('checkbox', { name: '기타' }));
    await user.type(
      screen.getByLabelText('기타 역량 설명 (선택)'),
      '3D 모델링',
    );
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
        skills: ['프로그래밍', '기타'],
        skillOther: '3D 모델링',
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
});
