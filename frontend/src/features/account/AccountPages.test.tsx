import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { fill, setupUser } from '@/test/user';
import { Route, Routes, useLocation } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import {
  LoginPage,
  ProfilePage,
  PublicProfilePage,
  SignupPage,
  ProfileVisibilityControl,
} from '@/features/account/AccountPages';
import { demoId, demoPassword } from '@/features/demo/auth-policy';
import { Avatar } from '@/components/common/CommonUi';
import { CreateTeamPage } from '@/features/teams/CreateTeamPage';
import { getPublicProfile, initialProfile } from '@/features/demo/data';
import {
  createDemoRecords,
  fixtureAcademicUnits,
  fixtureCatalogs,
  type DemoDatabase,
} from '@/features/demo/fixtures';
import type { Profile } from '@/features/profiles/api';
import {
  demoIds,
  ME,
  mockSession,
  myProfile,
  renderWithApi,
  sentRequests,
  settled,
  withProfile,
} from '@/test/render';

const weeklyAvailabilityOptions = fixtureCatalogs().weeklyAvailabilityRanges;
// 화면이 실제로 보낸 저장 요청(docs/api/profiles.md, docs/api/teams.md)
const requestsTo = (method: string, path: string) =>
  sentRequests.filter(
    (request) => request.method === method && request.path === path,
  );
const profileSaves = () => requestsTo('PUT', '/me/profile');
const visibilitySaves = () => requestsTo('PUT', '/me/profile/visibility');
const teamCreates = () => requestsTo('POST', '/teams');
const applyRequests = () =>
  sentRequests.filter(
    (request) =>
      request.method === 'POST' && request.path.endsWith('/applications'),
  );
const lastProfileSave = () => profileSaves().at(-1)?.body;
const withoutMyProfile = (): DemoDatabase => {
  const records = createDemoRecords();
  return {
    ...records,
    profiles: records.profiles.filter((item) => item.accountId !== ME),
  };
};

// 팀·소속·지원이 하나도 없는 목업 저장소(어느 공모전에서든 새 팀을 만들 수 있음)
const withoutTeams = (): DemoDatabase => ({
  ...createDemoRecords(),
  teams: [],
  memberships: [],
  applications: [],
  notifications: [],
});

// 상위 항목 이름까지 맞춰 학사 항목 ID를 찾습니다(같은 이름의 전공이 여러 학부에 있음).
const academicUnits = fixtureAcademicUnits();
const unitId = (name: string, parentName: string) => {
  const parent = academicUnits.find((unit) => unit.name === parentName)!;
  return academicUnits.find(
    (unit) => unit.name === name && unit.parentId === parent.id,
  )!.id;
};

function CurrentLocation() {
  const location = useLocation();
  return (
    <p>
      이동한 경로: {location.pathname}
      {location.search}
    </p>
  );
}

// 목업 API로 응답받는 계정 화면. 로그인·가입 화면은 비로그인, 그 외는 로그인 상태로 시작합니다.
async function renderAccount(
  path: string,
  options: {
    signedIn?: boolean;
    db?: DemoDatabase;
    /** 본인 프로필에 덮어쓸 값 */
    profile?: Partial<Profile>;
  } = {},
) {
  const signedIn =
    options.signedIn ?? !/^\/(login|signup)/.test(path.split('?')[0] ?? '');
  const records = options.db ?? createDemoRecords();
  const { client } = renderWithApi(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/profile/public" element={<PublicProfilePage />} />
      <Route path="/teams/new" element={<CreateTeamPage />} />
      <Route path="*" element={<CurrentLocation />} />
    </Routes>,
    {
      path,
      signedIn,
      db: options.profile ? withProfile(records, ME, options.profile) : records,
    },
  );
  await settled(client);
  return client;
}

async function enterLogin(user: ReturnType<typeof setupUser>) {
  await fill(user, screen.getByLabelText('아이디', { exact: true }), demoId);
  await fill(
    user,
    screen.getByLabelText('비밀번호', { exact: true }),
    demoPassword,
  );
}

async function renderProfileFlow() {
  renderWithApi(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/profile/public" element={<PublicProfilePage />} />
    </Routes>,
    { path: '/login?returnTo=%2Fprofile' },
  );
  await screen.findByRole('button', { name: '로그인' });
  const user = setupUser();
  await enterLogin(user);
  await user.click(screen.getByRole('button', { name: '로그인' }));
  await screen.findByRole('button', { name: '프로필 수정' });
}

describe('design preview account flows', () => {
  it.each([
    ['first profile', false, '/profile'],
    ['saved profile', true, '/profile'],
    ['profile edit', true, '/profile?edit=details'],
  ] as const)(
    'logs out from the %s without saving changes',
    async (_, hasProfile, path) => {
      await renderAccount(path, {
        db: hasProfile ? createDemoRecords() : withoutMyProfile(),
      });
      const user = setupUser();
      await user.click(screen.getByRole('button', { name: '로그아웃' }));
      await screen.findByText('로그인하고 계속해 주세요.');
      expect(mockSession()).toBeNull();
      expect(requestsTo('POST', '/auth/logout')).toHaveLength(1);
      expect(profileSaves()).toHaveLength(0);
      expect(screen.queryByLabelText('이름 (필수)')).not.toBeInTheDocument();
    },
  );

  it.each([true, false])(
    'uses API isDemo=%s across the profile summary, editor and public preview regardless of the name',
    async (isDemo) => {
      const client = await renderAccount('/profile', {
        profile: {
          realName: '시연 이름을 가진 사용자',
          isPublic: true,
          isDemo,
        },
      });
      const user = setupUser();
      expect(
        within(
          screen.getByRole('region', { name: '내 기본 정보' }),
        ).queryByText('시연 계정') !== null,
      ).toBe(isDemo);
      await user.click(screen.getByRole('button', { name: '프로필 수정' }));
      expect(screen.getByLabelText('이름 (필수)')).toHaveValue(
        '시연 이름을 가진 사용자',
      );
      expect(screen.queryByText('시연 계정') !== null).toBe(isDemo);
      await user.click(screen.getByRole('button', { name: '취소' }));
      await user.click(screen.getByRole('link', { name: '공개된 모습 보기' }));
      await settled(client);
      expect(
        within(
          screen.getByRole('region', { name: '공개된 내 프로필' }),
        ).queryByText('시연 계정') !== null,
      ).toBe(isDemo);
      expect(profileSaves()).toHaveLength(0);
      expect(visibilitySaves()).toHaveLength(0);
    },
  );

  it('projects every registered field of a public profile and none of a private profile', async () => {
    const profile = {
      ...initialProfile,
      academicStatusCode: 'enrolled',
      skillCodes: ['programming'],
      experienceBody: '프로젝트 경험',
      experienceState: 'provided' as const,
      portfolio: { url: 'https://example.com/work', title: '작업집' },
      isPublic: true,
    };
    expect(getPublicProfile(profile)).toEqual(profile);
    expect(getPublicProfile({ ...profile, isPublic: false })).toBeNull();
  });

  it('keeps character choices in the edit draft until saved and discards cancelled choices', async () => {
    await renderProfileFlow();
    const user = setupUser();
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
        .getByRole('heading', { name: initialProfile.realName })
        .closest('section')
        ?.querySelector('img'),
    ).toHaveAttribute('src', '/mascots/conver.png');
  });

  it('uses the default character when no optional avatar is selected', async () => {
    const { container } = render(<Avatar name="김지우" imageCode={null} />);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/mascots/skon.png',
    );
  });

  it.each([false, true])(
    'requires confirmation for a visibility change from %s and preserves cancelled changes',
    async (discoverable) => {
      await renderAccount('/profile', { profile: { isPublic: discoverable } });
      const user = setupUser();
      const toggle = screen.getByRole('switch', { name: '프로필 공개' });
      await user.click(toggle);
      expect(toggle).toHaveAttribute('aria-checked', String(discoverable));
      expect(visibilitySaves()).toEqual([]);
      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveAccessibleDescription(
        /이미 지원받은 팀장은 전체 현재 프로필을 볼 수 있고, AI 지원자 검토에도 최신 프로필/,
      );
      await user.click(within(dialog).getByRole('button', { name: '취소' }));
      await waitFor(() =>
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
      );
      expect(visibilitySaves()).toEqual([]);
      await user.click(toggle);
      await user.keyboard('{Escape}');
      await waitFor(() =>
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
      );
      expect(visibilitySaves()).toEqual([]);
      await user.click(toggle);
      await user.click(
        screen.getByRole('button', {
          name: discoverable ? '비공개로 전환' : '공개로 전환',
        }),
      );
      // docs/api/profiles.md#visibility-write: 현재 버전과 결정한 공개 상태만 보냅니다.
      await waitFor(() =>
        expect(visibilitySaves()).toEqual([
          {
            method: 'PUT',
            path: '/me/profile/visibility',
            body: { expectedVersion: '1', isPublic: !discoverable },
          },
        ]),
      );
    },
  );

  it('shows all saved fields after public confirmation and hides the entire preview after private confirmation', async () => {
    await renderProfileFlow();
    const user = setupUser();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    await fill(
      user,
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https://example.com/work',
    );
    await fill(
      user,
      screen.getByLabelText('포트폴리오 제목 (선택)'),
      '나의 작업',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await user.click(screen.getByRole('switch', { name: '프로필 공개' }));
    await user.click(screen.getByRole('button', { name: '공개로 전환' }));
    await user.click(screen.getByRole('link', { name: '공개된 모습 보기' }));
    expect(screen.getByText(initialProfile.introduction!)).toBeVisible();
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
    expect(
      screen.queryByText(initialProfile.introduction!),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /나의 작업/ }),
    ).not.toBeInTheDocument();
  });

  it('explains unavailable school verification in a dismissible popup without changing the profile', async () => {
    await renderAccount('/profile');
    const user = setupUser();
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
    expect(profileSaves()).toEqual([]);
  });

  it('starts with empty fields and reveals a password without submitting or changing it', async () => {
    await renderAccount('/login');
    const user = setupUser();
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
    expect(mockSession()).toBeNull();
  });

  it('reports invalid demo credentials and restores a working demo login', async () => {
    await renderAccount(`/login?from=%2Fteams%2F${demoIds.teams.makers}`);
    const user = setupUser();
    await fill(user, screen.getByLabelText('아이디'), '  DREAMONDEMO  ');
    await fill(user, screen.getByLabelText('비밀번호'), 'incorrect-password');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '아이디 또는 비밀번호를 확인',
    );
    expect(mockSession()).toBeNull();
    await user.clear(screen.getByLabelText('비밀번호'));
    await fill(user, screen.getByLabelText('비밀번호'), demoPassword);
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(
      await screen.findByText(`이동한 경로: /teams/${demoIds.teams.makers}`),
    ).toBeInTheDocument();
    expect(mockSession()).toBe(ME);
  });

  it.each([
    'https://example.com',
    '//example.com',
    '/../../private',
    '/\\example.com',
  ])('keeps login return path inside the app for %s', async (target) => {
    await renderAccount(`/login?returnTo=${encodeURIComponent(target)}`);
    const user = setupUser();
    await enterLogin(user);
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(
      await screen.findByText('이동한 경로: /workspace'),
    ).toBeInTheDocument();
  });

  it('preserves the original team destination when visiting signup and returning to login', async () => {
    await renderAccount(`/login?returnTo=%2Fteams%2F${demoIds.teams.makers}`);
    const user = setupUser();
    await user.click(screen.getByRole('link', { name: '회원가입' }));
    await user.click(screen.getByRole('link', { name: '로그인으로' }));
    await enterLogin(user);
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(
      await screen.findByText(`이동한 경로: /teams/${demoIds.teams.makers}`),
    ).toBeInTheDocument();
    expect(mockSession()).toBe(ME);
  });

  it('validates profile requirements and saves an optional portfolio without changing global privacy', async () => {
    await renderAccount('/profile', {
      profile: { weeklyAvailabilityCode: null },
    });
    const user = setupUser();
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
    expect(profileSaves()).toEqual([]);
    await fill(user, screen.getByLabelText('이름 (필수)'), '김예시');
    await fill(
      user,
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
    await fill(
      user,
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https://example.com/portfolio',
    );
    await user.selectOptions(
      screen.getByLabelText('주당 참여 가능 시간 (선택)'),
      '5~10시간 미만',
    );
    expect(profileSaves()).toEqual([]);
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      '프로필을 저장했어요.',
    );
    await waitFor(() =>
      expect(lastProfileSave()).toMatchObject({
        realName: '김예시',
        portfolio: { url: 'https://example.com/portfolio', title: null },
        weeklyAvailabilityCode: 'from_5_to_10',
      }),
    );
  });

  it('keeps weekly availability optional and discards unsaved changes', async () => {
    await renderAccount('/profile', {
      profile: { weeklyAvailabilityCode: 'from_10_to_20' },
    });
    const user = setupUser();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    const field = screen.getByLabelText('주당 참여 가능 시간 (선택)');
    expect(
      within(field)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual([
      '미입력',
      ...weeklyAvailabilityOptions.map((item) => item.displayName),
    ]);
    expect(field).toHaveAccessibleDescription(/참여 중인 모든 프로젝트를 합한/);
    await user.selectOptions(field, '20시간 이상');
    await user.click(screen.getByRole('button', { name: '취소' }));
    expect(profileSaves()).toEqual([]);
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    expect(screen.getByLabelText('주당 참여 가능 시간 (선택)')).toHaveValue(
      'from_10_to_20',
    );
    await user.selectOptions(
      screen.getByLabelText('주당 참여 가능 시간 (선택)'),
      '',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await waitFor(() =>
      expect(lastProfileSave()).toMatchObject({ weeklyAvailabilityCode: null }),
    );
  });

  it('retains portfolio edits only after saving and preserves the global privacy state', async () => {
    await renderProfileFlow();
    const user = setupUser();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    await fill(
      user,
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https://example.com/draft',
    );
    await user.click(screen.getByRole('button', { name: '취소' }));
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    expect(screen.getByLabelText('포트폴리오 링크 (선택)')).toHaveValue('');
    await fill(
      user,
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
    await renderAccount('/profile?edit=details');
    const user = setupUser();
    await fill(
      user,
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'javascript:alert(1)',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      screen.getByText(
        'http:// 또는 https://로 시작하는 링크를 입력해 주세요.',
      ),
    ).toBeVisible();
    expect(profileSaves()).toEqual([]);
  });

  it('clears the portfolio title when its URL is deleted', async () => {
    await renderAccount('/profile', {
      profile: {
        portfolio: { url: 'https://example.com/previous', title: '이전 제목' },
      },
    });
    const user = setupUser();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    await user.clear(screen.getByLabelText('포트폴리오 링크 (선택)'));
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await waitFor(() =>
      expect(lastProfileSave()).toMatchObject({ portfolio: null }),
    );
  });

  it('requires at least one profile role and permits cancellation without saving', async () => {
    await renderAccount('/profile');
    const user = setupUser();
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
    expect(profileSaves()).toEqual([]);
  });

  // docs/api/auth.md#account-endpoints: 가입 성공 시 바로 로그인, GET /me로 같은 계정을 확인한 뒤 프로필 설정
  it('signs up with automatic sign-in, verifies the account and saves the first profile without credentials', async () => {
    await renderAccount('/signup');
    const user = setupUser();
    await fill(user, screen.getByLabelText('아이디 (필수)'), '  NewAccount  ');
    await fill(user, screen.getByLabelText('비밀번호 (필수)'), 'abcdefg!');
    await fill(user, screen.getByLabelText('이름 (필수)'), '김지우');
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
    const account = requestsTo('POST', '/accounts');
    expect(account).toEqual([
      {
        method: 'POST',
        path: '/accounts',
        body: {
          loginId: 'newaccount',
          password: 'abcdefg!',
        },
      },
    ]);
    expect(mockSession()).not.toBeNull();
    expect(mockSession()).not.toBe(ME);
    await waitFor(() => expect(profileSaves()).toHaveLength(1));
    const saved = lastProfileSave();
    expect(saved).toMatchObject({
      expectedVersion: '0',
      realName: '김지우',
      fieldCodes: ['education'],
      roleCodes: ['planning'],
    });
    expect(saved).not.toHaveProperty('password');
    expect(saved).not.toHaveProperty('loginId');
    expect(screen.queryByLabelText('비밀번호 (필수)')).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '프로필 완성하기' }),
    ).toHaveAttribute('href', '/profile?edit=details');
  });

  it('keeps signed-out team creation behind login and preserves the contest choice', async () => {
    await renderAccount(`/teams/new?contest=${demoIds.contests.campus}`, {
      signedIn: false,
    });
    expect(screen.queryByLabelText('팀 이름')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인하기' })).toHaveAttribute(
      'href',
      `/login?returnTo=%2Fteams%2Fnew%3Fcontest%3D${demoIds.contests.campus}`,
    );
    expect(teamCreates()).toEqual([]);
  });

  it('validates team fields, creates the chosen contest team and navigates to its own detail', async () => {
    await renderAccount(`/teams/new?contest=${demoIds.contests.green}`, {
      db: withoutTeams(),
    });
    const user = setupUser();
    expect(screen.getByLabelText('참여 공모전')).toHaveTextContent(
      '일상 속 그린테크 챌린지',
    );
    await user.click(screen.getByRole('button', { name: '팀 만들기' }));
    expect(
      await screen.findByText('팀 이름을 2자 이상 입력해 주세요.'),
    ).toBeInTheDocument();
    expect(teamCreates()).toEqual([]);
    await fill(user, screen.getByLabelText('팀 이름'), '새로운 예시 팀');
    await fill(
      user,
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
    // 서버가 발급한 새 팀 ID의 팀 공간으로 이동
    expect(
      await screen.findByText(
        /이동한 경로: \/teams\/[0-9a-f-]{36}\?view=space/,
      ),
    ).toBeInTheDocument();
    // docs/api/teams.md#team-create: POST /teams 본문(정원은 십진 문자열)
    expect(teamCreates()).toEqual([
      {
        method: 'POST',
        path: '/teams',
        body: {
          requestId: expect.any(String),
          contestId: demoIds.contests.green,
          name: '새로운 예시 팀',
          introduction: '환경 문제를 함께 해결해요.',
          capacity: '3',
          roleCodes: ['development'],
          recruitmentDeadline: { date: '2026-10-24' },
        },
      },
    ]);
  });

  it('requires a known contest and preserves the team draft while searching and changing it', async () => {
    await renderAccount('/teams/new?contest=unknown', {
      db: withoutTeams(),
    });
    const user = setupUser();
    const trigger = screen.getByLabelText('참여 공모전');
    await fill(user, screen.getByLabelText('팀 이름'), '검색해서 만든 팀');
    await fill(
      user,
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
      await within(drawer).findByRole('option', {
        name: /우리 동네를 새롭게, 로컬 브랜딩/,
      }),
    );
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    expect(teamCreates()).toEqual([]);
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
      expect(teamCreates().map((request) => request.body)).toEqual([
        {
          requestId: expect.any(String),
          contestId: demoIds.contests.local,
          name: '검색해서 만든 팀',
          introduction: '함께 자료를 조사하고 정리해요.',
          capacity: '3',
          roleCodes: ['development'],
          recruitmentDeadline: { date: '2026-11-01' },
        },
      ]),
    );
  });

  // Codex 리뷰 P2: 접수 중 공모전 첫 100건 밖의 공모전도 URL로 미리 선택하고 선택창 검색으로 찾을 수 있습니다.
  it('preselects and finds an open contest outside the first 100 results', async () => {
    const records = withoutTeams();
    const base = records.contests.find(
      (item) => item.id === demoIds.contests.local,
    )!;
    // 등록 최신순에서 맨 뒤(101번째 이후)에 오는 접수 중 공모전
    const extra = Array.from({ length: 101 }, (_, index) => ({
      ...base,
      id: `00000000-0000-4000-8000-${(index + 1).toString(16).padStart(12, '0')}`,
      title: `추가 공모전 ${String(index).padStart(3, '0')}`,
      createdAt: new Date(Date.parse(base.createdAt) + (index + 1) * 60_000)
        .toISOString()
        .replace('.000Z', 'Z'),
    }));
    await renderAccount(`/teams/new?contestId=${demoIds.contests.local}`, {
      db: { ...records, contests: [...records.contests, ...extra] },
    });
    const user = setupUser();
    const trigger = screen.getByLabelText('참여 공모전');
    expect(trigger).toHaveTextContent('우리 동네를 새롭게, 로컬 브랜딩');
    await user.click(trigger);
    const drawer = await screen.findByRole('dialog', { name: '공모전 선택' });
    // 첫 페이지에는 최근 등록한 추가 공모전만 보입니다.
    await waitFor(() =>
      expect(within(drawer).getAllByRole('option')).toHaveLength(20),
    );
    expect(
      within(drawer).queryByRole('option', { name: /로컬 브랜딩/ }),
    ).not.toBeInTheDocument();
    await user.type(
      within(drawer).getByRole('combobox', { name: '공모전 검색' }),
      '로컬 브랜딩',
    );
    expect(
      await within(drawer).findByRole('option', {
        name: /우리 동네를 새롭게, 로컬 브랜딩.*현재 선택됨/,
      }),
    ).toBeInTheDocument();
  });

  // PR #121 리뷰: 현재 공모전을 다시 고르면 입력한 정원·역할을 유지하고, 다른 공모전일 때만 초기화한다.
  it('keeps capacity and roles when the same contest is chosen again and resets them for a different contest', async () => {
    await renderAccount(`/teams/new?contestId=${demoIds.contests.campus}`, {
      db: withoutTeams(),
    });
    const user = setupUser();
    const capacity = screen.getByLabelText('팀장 포함 총 정원');
    await user.type(capacity, '4');
    const planning = () =>
      within(screen.getByRole('group', { name: /모집할 역할/ })).getByLabelText(
        '기획',
      );
    await user.click(planning());
    expect(planning()).toBeChecked();

    const chooseContest = async (name: RegExp) => {
      await user.click(screen.getByLabelText('참여 공모전'));
      const drawer = await screen.findByRole('dialog', { name: '공모전 선택' });
      await user.click(within(drawer).getByRole('option', { name }));
      await waitFor(() => expect(drawer).not.toBeInTheDocument());
    };

    await chooseContest(/더 나은 캠퍼스 아이디어 공모전/);
    expect(capacity).toHaveValue(4);
    expect(planning()).toBeChecked();

    await chooseContest(/우리 동네를 새롭게, 로컬 브랜딩/);
    expect(capacity).toHaveValue(null);
    expect(
      screen.queryByRole('group', { name: /모집할 역할/ }),
    ).not.toBeInTheDocument();
  });

  // PR #121 리뷰: 폼이 허용한 주소는 저장 시 정규화해 내 프로필과 공개 미리보기에 같은 링크를 보여준다.
  it('normalizes an accepted portfolio URL so the saved and public links match', async () => {
    await renderProfileFlow();
    const user = setupUser();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    await fill(
      user,
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https:/example.com/portfolio',
    );
    await fill(
      user,
      screen.getByLabelText('포트폴리오 제목 (선택)'),
      '나의 작업',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(screen.getByRole('link', { name: /나의 작업/ })).toHaveAttribute(
      'href',
      'https://example.com/portfolio',
    );
    await user.click(screen.getByRole('switch', { name: '프로필 공개' }));
    await user.click(screen.getByRole('button', { name: '공개로 전환' }));
    await user.click(screen.getByRole('link', { name: '공개된 모습 보기' }));
    expect(screen.getByRole('link', { name: /나의 작업/ })).toHaveAttribute(
      'href',
      'https://example.com/portfolio',
    );
  });

  // PR #121 리뷰: 비로그인으로 연 프로필 보완 화면은 로그인 후 편집 상태와 팀 복귀 경로를 유지한다.
  it('keeps the profile edit intent and team return path through login', async () => {
    renderWithApi(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="*" element={<CurrentLocation />} />
      </Routes>,
      {
        path: `/profile?edit=details&returnTo=%2Fteams%2F${demoIds.teams.makers}`,
      },
    );
    const user = setupUser();
    const login = await screen.findByRole('link', { name: '로그인' });
    expect(login).toHaveAttribute(
      'href',
      `/login?returnTo=${encodeURIComponent(`/profile?edit=details&returnTo=%2Fteams%2F${demoIds.teams.makers}`)}`,
    );
    await user.click(login);
    await enterLogin(user);
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(
      await screen.findByRole('heading', { name: '프로필 수정' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      await screen.findByText(`이동한 경로: /teams/${demoIds.teams.makers}`),
    ).toBeInTheDocument();
  });

  it('keeps the global privacy state when saving profile details without field-level toggles', async () => {
    await renderAccount('/profile?edit=details');
    const user = setupUser();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    // docs/api/profiles.md: 공개 상태는 별도 요청(PUT /me/profile/visibility)으로만 바뀝니다.
    await waitFor(() => expect(profileSaves()).toHaveLength(1));
    expect(lastProfileSave()).not.toHaveProperty('isPublic');
    expect(visibilitySaves()).toEqual([]);
    expect(myProfile().isPublic).toBe(false);
  });

  it('clears dependent selections when the college changes, and skips majors for an independent department', async () => {
    await renderAccount('/profile?edit=details');
    const user = setupUser();
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
    await waitFor(() =>
      expect(lastProfileSave()).toMatchObject({
        academicUnitId: unitId('소프트웨어학과', '이공대학'),
      }),
    );
  });

  it('preserves a stored legacy affiliation while other profile fields change', async () => {
    // 더 이상 새로 선택할 수 없는(isSelectable=false) 과거 학사 항목(GET /catalogs/academic-units 응답)
    const legacy = [
      { id: '9001', name: '과거 대학', parentId: null, isSelectable: false },
      { id: '9002', name: '과거 학부', parentId: '9001', isSelectable: false },
      { id: '9003', name: '과거 전공', parentId: '9002', isSelectable: false },
    ];
    const records = createDemoRecords();
    await renderAccount('/profile?edit=details', {
      db: { ...records, academicUnits: [...records.academicUnits, ...legacy] },
      profile: { academicUnitId: '9003' },
    });
    const user = setupUser();
    expect(
      screen.getByRole('option', { name: '과거 대학 (기존 소속)' }),
    ).toBeDisabled();
    await fill(user, screen.getByLabelText('자기소개 (선택)'), ' 새로운 소개');
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await waitFor(() =>
      expect(lastProfileSave()).toMatchObject({ academicUnitId: '9003' }),
    );
  });

  it('distinguishes no experience, removes other choices and saves optional skills and portfolio title', async () => {
    await renderAccount('/profile?edit=details');
    const user = setupUser();
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
    await fill(
      user,
      screen.getByLabelText('포트폴리오 링크 (선택)'),
      'https://example.com/work',
    );
    await fill(
      user,
      screen.getByLabelText('포트폴리오 제목 (선택)'),
      '나의 작업',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await waitFor(() =>
      expect(lastProfileSave()).toMatchObject({
        experienceState: 'none',
        experienceBody: null,
        skillCodes: ['programming'],
        portfolio: { url: 'https://example.com/work', title: '나의 작업' },
      }),
    );
  });

  it('returns to the team after required profile completion without submitting an application', async () => {
    await renderAccount(
      `/profile?edit=details&returnTo=%2Fteams%2F${demoIds.teams.makers}`,
      // 필수 프로필이 아직 없는 계정(GET /me/profile 404)
      { db: withoutMyProfile() },
    );
    const user = setupUser();
    await fill(user, screen.getByLabelText('이름 (필수)'), '김지우');
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
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      await screen.findByText(`이동한 경로: /teams/${demoIds.teams.makers}`),
    ).toBeInTheDocument();
    expect(applyRequests()).toEqual([]);
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
      await renderAccount('/profile?edit=details');
      const user = setupUser();
      const field = screen.getByLabelText(label);
      const oversized = '가'.repeat(max + 1);
      fireEvent.change(field, { target: { value: oversized } });
      await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
      expect(await screen.findByText(message)).toBeVisible();
      expect(field).toHaveValue(oversized);
      expect(field).toHaveAttribute('aria-invalid', 'true');
      expect(profileSaves()).toEqual([]);
    },
  );

  it('validates profile selection maximums and keeps all invalid choices for correction', async () => {
    await renderAccount('/profile?edit=details');
    const user = setupUser();
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
    expect(profileSaves()).toEqual([]);
    await user.click(within(roles).getByLabelText('발표'));
    await user.click(within(interests).getByLabelText('디자인'));
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await waitFor(() => expect(profileSaves()).toHaveLength(1));
  });

  it('treats blank experience as unspecified, trims saved text and permits omitted academics', async () => {
    await renderAccount('/profile?edit=details', {
      profile: { experienceState: 'provided', experienceBody: '이전 경험' },
    });
    const user = setupUser();
    fireEvent.change(screen.getByLabelText('이름 (필수)'), {
      target: { value: '  김지우  ' },
    });
    fireEvent.change(screen.getByLabelText('관련 경험 (선택)'), {
      target: { value: '   ' },
    });
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await waitFor(() =>
      expect(lastProfileSave()).toMatchObject({
        realName: '김지우',
        experienceBody: null,
        experienceState: 'unspecified',
        academicStatusCode: null,
        gradeCode: null,
      }),
    );
  });

  it('preserves valid academic descendants when the same parent relationship is selected', async () => {
    await renderAccount('/profile?edit=details', {
      profile: { academicUnitId: unitId('경영학전공', '경영학부') },
    });
    const user = setupUser();
    await user.selectOptions(
      screen.getByLabelText('단과대학 (선택)'),
      '인문사회과학대학',
    );
    await user.selectOptions(
      screen.getByLabelText('학부·학과 (선택)'),
      '경영학부',
    );
    expect(screen.getByLabelText('세부전공 (선택)')).toHaveValue(
      unitId('경영학전공', '경영학부'),
    );
    await user.selectOptions(
      screen.getByLabelText('학부·학과 (선택)'),
      '공공인재학부',
    );
    expect(screen.getByLabelText('세부전공 (선택)')).toHaveValue('');
    await user.click(screen.getByRole('button', { name: '취소' }));
    expect(profileSaves()).toEqual([]);
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
    const user = setupUser();
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
  it('normalizes duplicate signup IDs and preserves pasted over-limit passwords for correction', async () => {
    await renderAccount('/signup');
    const user = setupUser();
    const username = screen.getByLabelText('아이디 (필수)');
    await user.click(username);
    await user.paste('  DREAMONDEMO  ');
    await user.tab();
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
    expect(profileSaves()).toEqual([]);
  });

  it('updates password requirements while typing without premature errors or repeated ID checks', async () => {
    await renderAccount('/signup');
    const user = setupUser();
    const requirements = screen.getByRole('list', { name: '비밀번호 조건' });
    const states = () =>
      within(requirements)
        .getAllByRole('listitem')
        .map((item) => item.textContent);
    expect(states()).toEqual([
      '8자 이상미충족',
      '기호 1개 이상 (!, @, # 등)미충족',
    ]);
    await fill(user, screen.getByLabelText('아이디 (필수)'), 'livechecks');
    const password = screen.getByLabelText('비밀번호 (필수)');
    await user.click(password);
    await user.type(password, 'abcdefgh');
    expect(states()).toEqual([
      '8자 이상충족',
      '기호 1개 이상 (!, @, # 등)미충족',
    ]);
    expect(password).toHaveAttribute('aria-invalid', 'false');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await user.type(password, '!');
    expect(states()).toEqual([
      '8자 이상충족',
      '기호 1개 이상 (!, @, # 등)충족',
    ]);
    await user.keyboard('{Backspace}');
    expect(states()[1]).toContain('미충족');
    await user.tab();
    expect(
      await screen.findByText('기호를 1개 이상 포함해 주세요. (!, @, # 등)'),
    ).toBeVisible();
    expect(requestsTo('GET', '/auth/login-id-availability')).toHaveLength(1);
    expect(requestsTo('POST', '/accounts')).toEqual([]);
  });

  it('preserves forbidden password characters and immediately explains how to correct them', async () => {
    await renderAccount('/signup');
    const user = setupUser();
    const password = screen.getByLabelText('비밀번호 (필수)');
    for (const value of ['abcdef가!', ' abcdefg!', 'abcdefg! ', 'abc defg!']) {
      await user.clear(password);
      await fill(user, password, value);
      expect(password).toHaveValue(value);
      expect(password).toHaveAttribute('aria-invalid', 'true');
      expect(screen.getByText('한글과 공백은 사용할 수 없어요.')).toBeVisible();
    }
    await user.clear(password);
    await fill(user, password, 'abcdefg!');
    expect(
      screen.queryByText('한글과 공백은 사용할 수 없어요.'),
    ).not.toBeInTheDocument();
    expect(password).toHaveAttribute('aria-invalid', 'false');
    expect(requestsTo('POST', '/accounts')).toEqual([]);
  });

  it('shows Caps Lock only when detected and clears it on key release or lost focus', async () => {
    await renderAccount('/signup');
    const user = setupUser();
    const password = screen.getByLabelText('비밀번호 (필수)');
    const notice = 'Caps Lock이 켜져 있어요.';
    expect(screen.queryByText(notice)).not.toBeInTheDocument();
    await user.click(password);
    fireEvent.keyDown(password, { key: 'A', modifierCapsLock: true });
    expect(screen.getByText(notice)).toBeVisible();
    expect(password).toHaveAccessibleDescription(
      expect.stringContaining(notice),
    );
    fireEvent.keyUp(password, { key: 'CapsLock', modifierCapsLock: false });
    expect(screen.queryByText(notice)).not.toBeInTheDocument();
    fireEvent.keyUp(password, { key: 'CapsLock', modifierCapsLock: true });
    expect(screen.getByText(notice)).toBeVisible();
    await user.click(screen.getByLabelText('이름 (필수)'));
    expect(screen.queryByText(notice)).not.toBeInTheDocument();
    await user.click(password);
    fireEvent.keyDown(password, { key: 'A', modifierCapsLock: true });
    fireEvent(window, new Event('blur'));
    expect(screen.queryByText(notice)).not.toBeInTheDocument();
    expect(password).toHaveValue('');
    expect(requestsTo('POST', '/accounts')).toEqual([]);
  });
});
