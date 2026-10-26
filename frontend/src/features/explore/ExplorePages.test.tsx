import { screen, within } from '@testing-library/react';
import { setupUser } from '@/test/user';
import { Route, Routes, useLocation } from 'react-router';
import { describe, expect, it } from 'vitest';
import {
  ContestPage,
  ExplorePage,
  PersonPage,
} from '@/features/explore/ExplorePages';
import { TeamPage } from '@/features/workspace/WorkspacePages';
import { archivedContest, contests, people } from '@/features/demo/data';
import {
  createDemoRecords,
  fixtureAcademicUnits,
  type DemoDatabase,
  type MembershipRecord,
  type TeamRecord,
} from '@/features/demo/fixtures';
import type { Profile } from '@/features/profiles/api';
import {
  demoIds,
  myProfile,
  recordsWithMyProfile,
  renderWithApi,
  settled,
} from '@/test/render';

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

// 목업 API(목업 저장소)로 응답받는 탐색 화면. 요청이 끝날 때까지 기다린 뒤 확인합니다.
async function renderExplore(
  path: string,
  options: { signedIn?: boolean; db?: DemoDatabase } = {},
) {
  const { client } = renderWithApi(
    <>
      <CurrentLocation />
      <Routes>
        <Route path="/explore" element={<ExplorePage />} />
        <Route path="/people/:personId" element={<PersonPage />} />
        <Route path="/contests/:contestId" element={<ContestPage />} />
        <Route path="/teams/:teamId" element={<TeamPage />} />
      </Routes>
    </>,
    { path, signedIn: options.signedIn ?? false, db: options.db },
  );
  await screen.findByLabelText('현재 경로');
  await settled(client);
  // 사용자 조작 뒤 다음 요청이 끝날 때까지 기다립니다.
  const user = setupUser();
  const step = async (action: () => Promise<void>) => {
    await action();
    await settled(client);
  };
  return { user, step, client };
}

const visualMajor = fixtureAcademicUnits().find(
  (unit) => unit.name === '시각정보디자인전공',
)!;
// 본인 프로필에 등록 가능한 모든 항목을 채운 값
const publicPatch: Partial<Profile> = {
  realName: '공개검색검증사용자',
  academicStatusCode: 'enrolled',
  gradeCode: 'year_3',
  academicUnitId: visualMajor.id,
  skillCodes: ['data_visualization'],
  introduction: '사용자인터뷰를 함께 진행하고 싶어요.',
  experienceBody: '졸업전시기획 프로젝트',
  experienceState: 'provided',
  weeklyAvailabilityCode: 'from_5_to_10',
  portfolio: {
    url: 'https://portfolio.example.com/jiwoo',
    title: '캠퍼스작업집',
  },
  isPublic: true,
};

// ─── 목업 저장소 시드: 팀과 팀장 소속 ───
const uuid = (index: number) =>
  `12345678-0000-4000-8000-${String(index).padStart(12, '0')}`;
const makers = createDemoRecords().teams.find(
  (team) => team.id === demoIds.teams.makers,
)!;
type TeamSeed = Partial<TeamRecord> & { members?: number };
function withTeams(seeds: TeamSeed[], keep: string[] = []): DemoDatabase {
  const records = createDemoRecords();
  const teams: TeamRecord[] = [];
  const memberships: MembershipRecord[] = [];
  seeds.forEach(({ members = 1, ...seed }, index) => {
    const team: TeamRecord = {
      ...makers,
      id: uuid(index + 1),
      ownerAccountId: demoIds.accounts.doyun,
      // 먼저 넣은 팀이 최신(createdAt DESC 정렬에서 앞)
      createdAt: new Date(Date.parse('2026-10-17T00:00:00Z') - index * 60_000)
        .toISOString()
        .replace('.000Z', 'Z'),
      ...seed,
    };
    teams.push(team);
    for (let member = 0; member < members; member += 1)
      memberships.push({
        membershipId: uuid(1000 + index * 10 + member),
        teamId: team.id,
        accountId:
          member === 0
            ? team.ownerAccountId
            : [
                demoIds.accounts.jiho,
                demoIds.accounts.yuna,
                demoIds.accounts.haneul,
              ][member - 1]!,
        membershipRole: member === 0 ? 'leader' : 'member',
        roleCode: member === 0 ? null : 'planning',
        joinedAt: team.createdAt,
        endedAt: null,
      });
  });
  return {
    ...records,
    teams: [
      ...records.teams.filter((team) => keep.includes(team.id)),
      ...teams,
    ],
    memberships: [
      ...records.memberships.filter((item) => keep.includes(item.teamId)),
      ...memberships,
    ],
    applications: records.applications.filter((item) =>
      keep.includes(item.teamId),
    ),
    notifications: [],
  };
}
const pagedNames = Array.from(
  { length: 14 },
  (_, index) => `페이지 팀 ${String(index + 1).padStart(2, '0')}`,
);
const pagedSeeds: TeamSeed[] = pagedNames.map((name) => ({
  name,
  roleCodes: ['development', 'design'],
}));
const pagedTeamId = (name: string) => uuid(pagedNames.indexOf(name) + 1);
const level3Headings = () =>
  screen.getAllByRole('heading', { level: 3 }).map((node) => node.textContent);

describe('official reference public exploration', () => {
  it('allows guests to read and filter public contests using the shared interests', async () => {
    const { user, step } = await renderExplore('/explore');
    expect(
      screen.getByRole('heading', { name: contests[0]!.title }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '탐색 필터' }));
    await user.click(screen.getByRole('radio', { name: '교육' }));
    await step(() =>
      user.click(screen.getByRole('button', { name: '필터 적용' })),
    );
    // docs/api/contests.md#queries: 상태를 지정하지 않으면 예정·진행·마감 공고를 모두 보여줍니다(마감 공고 포함).
    expect(screen.getByRole('status')).toHaveTextContent('검색 결과 3개');
    expect(
      screen.getByRole('heading', { name: contests[0]!.title }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: archivedContest.title }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: contests[1]!.title }),
    ).not.toBeInTheDocument();
  });

  it('discards filter drafts and clears applied filters while retaining the selected tab', async () => {
    const { user, step } = await renderExplore(
      '/explore?tab=teams&role=development&open=true',
    );
    await user.click(screen.getByRole('button', { name: '탐색 필터' }));
    await user.click(screen.getByRole('radio', { name: '디자인' }));
    await user.click(screen.getByRole('button', { name: '취소' }));
    await user.click(screen.getByRole('button', { name: '탐색 필터' }));
    expect(screen.getByRole('radio', { name: '개발' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '모집중만' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: '취소' }));
    await step(() =>
      user.click(screen.getByRole('button', { name: '검색 조건 초기화' })),
    );
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
    const { user, step } = await renderExplore('/explore?sort=deadline');
    expect(
      screen.getByRole('link', { name: 'AI에게 추천 받기' }),
    ).toHaveAttribute('href', '/ai');
    await step(() =>
      user.click(screen.getByRole('button', { name: '검색 조건 초기화' })),
    );
    expect(screen.getByLabelText('정렬')).toHaveValue('default');
    expect(
      screen.queryByRole('button', { name: '검색 조건 초기화' }),
    ).not.toBeInTheDocument();
  });

  it('keeps public team recruitment visible to guests without exposing team space', async () => {
    await renderExplore('/explore?tab=teams');
    const link = screen.getByRole('link', { name: /캠퍼스 메이커스/ });
    expect(link).toHaveAttribute(
      'href',
      `/teams/${demoIds.teams.makers}?from=%2Fexplore%3Ftab%3Dteams`,
    );
    expect(
      screen.queryByRole('link', { name: /팀 공간/ }),
    ).not.toBeInTheDocument();
  });

  it('paginates the complete filtered result and preserves its conditions and page through team detail', async () => {
    const params = new URLSearchParams({
      tab: 'teams',
      q: '페이지',
      role: 'development',
      open: 'true',
      contest: demoIds.contests.campus,
      page: '2',
    });
    const { user, step } = await renderExplore(`/explore?${params}`, {
      db: withTeams(pagedSeeds, [demoIds.teams.greenwave]),
    });
    const nav = screen.getByRole('navigation', { name: '탐색 결과 페이지' });
    expect(screen.getByRole('status')).toHaveTextContent('검색 결과 14개');
    expect(level3Headings()).toEqual(pagedNames.slice(6, 12));
    expect(within(nav).getByRole('link', { name: '2페이지' })).toHaveAttribute(
      'aria-current',
      'page',
    );

    await step(() =>
      user.click(within(nav).getByRole('link', { name: '다음 페이지' })),
    );
    expect(level3Headings()).toEqual(pagedNames.slice(12));
    expect(
      screen.getByRole('heading', { name: '함께 도전하는 팀' }),
    ).toHaveFocus();
    const expectedLastPage = new URLSearchParams(params);
    expectedLastPage.set('page', '3');
    expect(currentUrl().searchParams.toString()).toBe(
      expectedLastPage.toString(),
    );
    expect(screen.getByRole('button', { name: '다음 페이지' })).toBeDisabled();

    await step(() =>
      user.click(screen.getByRole('link', { name: '이전 페이지' })),
    );
    const listPath = currentUrl().pathname + currentUrl().search;
    const teamLink = screen.getByRole('link', { name: /페이지 팀 07/ });
    expect(
      new URL(
        teamLink.getAttribute('href')!,
        'https://example.com',
      ).searchParams.get('from'),
    ).toBe(listPath);
    expect(teamLink.getAttribute('href')).toContain(
      `/teams/${pagedTeamId('페이지 팀 07')}`,
    );
    await step(() => user.click(teamLink));
    expect(
      screen.getByRole('heading', { name: '페이지 팀 07' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute(
      'href',
      listPath,
    );
    await step(() =>
      user.click(screen.getByRole('link', { name: '목록으로' })),
    );
    expect(currentUrl().searchParams.toString()).toBe(params.toString());
    expect(level3Headings()).toEqual(pagedNames.slice(6, 12));
  });

  it.each(['search', 'filter', 'tab', 'reset'])(
    'returns to page one when the user changes %s',
    async (action) => {
      const { user, step } = await renderExplore(
        '/explore?tab=teams&q=페이지&role=development&page=2',
        { signedIn: true, db: withTeams(pagedSeeds) },
      );
      expect(currentUrl().searchParams.get('page')).toBe('2');
      if (action === 'search') {
        await step(() =>
          user.type(screen.getByRole('textbox', { name: '탐색 검색' }), ' '),
        );
      } else if (action === 'filter') {
        await user.click(screen.getByRole('button', { name: '탐색 필터' }));
        await user.click(screen.getByRole('radio', { name: '디자인' }));
        await step(() =>
          user.click(screen.getByRole('button', { name: '필터 적용' })),
        );
        expect(currentUrl().searchParams.get('role')).toBe('design');
      } else if (action === 'tab') {
        await step(() =>
          user.click(screen.getByRole('link', { name: '사람' })),
        );
        expect(
          screen.getByRole('heading', { name: '함께할 사람' }),
        ).toBeInTheDocument();
      } else {
        await step(() =>
          user.click(screen.getByRole('button', { name: '검색 조건 초기화' })),
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
    async ({ requested, expectedPage }) => {
      const { client } = await renderExplore(
        `/explore?tab=teams&role=development&page=${requested}`,
        { db: withTeams(pagedSeeds) },
      );
      await settled(client);
      expect(currentUrl().searchParams.get('page')).toBe(
        expectedPage === 1 ? null : String(expectedPage),
      );
      expect(currentUrl().searchParams.get('tab')).toBe('teams');
      expect(currentUrl().searchParams.get('role')).toBe('development');
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

  it('does not expose people or their search matches to guests', async () => {
    await renderExplore('/explore?tab=people&q=정수아');
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
        screen.queryByRole('heading', { name: person.realName }),
      ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인하기' })).toHaveAttribute(
      'href',
      '/login?returnTo=%2Fexplore%3Ftab%3Dpeople',
    );
  });

  it('provides the AI shortcut in people search for both guests and members', async () => {
    await renderExplore('/explore?tab=people', { signedIn: true });
    expect(
      screen.getByRole('link', { name: 'AI에게 추천 받기' }),
    ).toHaveAttribute('href', '/ai');
  });

  it('guards direct people detail links and keeps the target for login', async () => {
    await renderExplore(`/people/${demoIds.accounts.sua}`);
    expect(
      screen.getByRole('heading', { name: '로그인이 필요해요' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('정수아')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '희망 역할' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인하기' })).toHaveAttribute(
      'href',
      `/login?returnTo=%2Fpeople%2F${demoIds.accounts.sua}`,
    );
  });

  it('does not create a public detail for a profile excluded from people exploration', async () => {
    await renderExplore(`/people/${demoIds.accounts.me}`, { signedIn: true });
    expect(
      screen.getByRole('heading', { name: '프로필을 찾을 수 없어요' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(myProfile().realName)).not.toBeInTheDocument();
  });

  it.each(['공개검색검증사용자', '졸업전시기획', 'portfolio.example.com'])(
    'excludes a private profile from search regardless of the matching field: %s',
    async (query) => {
      await renderExplore(
        `/explore?tab=people&q=${encodeURIComponent(query)}`,
        {
          signedIn: true,
          db: recordsWithMyProfile({ ...publicPatch, isPublic: false }),
        },
      );
      expect(
        screen.getByRole('heading', { name: '검색 결과가 없어요' }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole('heading', { name: publicPatch.realName }),
      ).not.toBeInTheDocument();
    },
  );

  // docs/api/profiles.md#directory-endpoints: q는 이름·자기소개·분야·역할·역량의 표시명을 검색합니다.
  it.each(['공개검색검증사용자', '사용자인터뷰', '데이터 시각화', 'IT·기술'])(
    'finds a public profile by the searchable profile information: %s',
    async (query) => {
      await renderExplore(
        `/explore?tab=people&q=${encodeURIComponent(query)}`,
        { signedIn: true, db: recordsWithMyProfile(publicPatch) },
      );
      expect(
        screen.getByRole('heading', { name: publicPatch.realName }),
      ).toBeInTheDocument();
    },
  );

  it.each(['재학', '시각정보디자인전공', '졸업전시기획', '5~10시간 미만'])(
    'does not search details outside the people search contract: %s',
    async (query) => {
      await renderExplore(
        `/explore?tab=people&q=${encodeURIComponent(query)}`,
        { signedIn: true, db: recordsWithMyProfile(publicPatch) },
      );
      expect(
        screen.queryByRole('heading', { name: publicPatch.realName }),
      ).not.toBeInTheDocument();
    },
  );

  it('shows every registered public profile field including the schedule and portfolio link', async () => {
    await renderExplore(`/people/${demoIds.accounts.me}`, {
      signedIn: true,
      db: recordsWithMyProfile(publicPatch),
    });
    expect(
      screen.getByRole('heading', { name: publicPatch.realName }),
    ).toBeInTheDocument();
    for (const value of [
      '재학',
      '3학년',
      '디자인&영상대학',
      '디자인학부',
      '시각정보디자인전공',
      '데이터 시각화',
      'IT·기술',
      '교육',
      publicPatch.introduction!,
      publicPatch.experienceBody!,
      '5~10시간 미만',
    ])
      expect(screen.getByText(value)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /캠퍼스작업집/ })).toHaveAttribute(
      'href',
      publicPatch.portfolio!.url,
    );
    expect(screen.getByRole('link', { name: /캠퍼스작업집/ })).toHaveAttribute(
      'target',
      '_blank',
    );
  });

  it('keeps closed contest history readable with its source while preventing new participation actions', async () => {
    await renderExplore(`/contests/${demoIds.contests.archive}`);
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
    ).toHaveAttribute('href', archivedContest.sourceUrl);
    expect(
      screen.queryByRole('link', { name: '팀 만들기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '팀 찾기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '준비 모임 만들기' }),
    ).not.toBeInTheDocument();
  });

  it('shows the official entry size, submission material and dates separately from team recruitment', async () => {
    await renderExplore(`/contests/${demoIds.contests.campus}`);
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
      `/teams/new?contest=${demoIds.contests.campus}`,
    );
  });

  it('shows only this contest’s teams inline with accessible create and AI icon actions', async () => {
    await renderExplore(`/contests/${demoIds.contests.campus}`);
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
    expect(create).toHaveAttribute(
      'href',
      `/teams/new?contest=${demoIds.contests.campus}`,
    );
    expect(create.textContent).toBe('');
    const ai = within(teamSection).getByRole('link', {
      name: 'AI로 팀 찾아보기',
    });
    expect(ai).toHaveAttribute('href', '/ai');
    expect(ai.textContent).toBe('');
  });

  it.each([
    {
      contestId: demoIds.contests.campus,
      action: '팀 만들기',
      prompt: '첫 팀을 만들어 함께 도전해 보세요.',
    },
    {
      contestId: demoIds.contests.local,
      action: '팀 만들기',
      prompt: '첫 팀을 만들어 함께 도전해 보세요.',
    },
  ])(
    'invites users to create the first group when $contestId has no teams',
    async ({ contestId, action, prompt }) => {
      await renderExplore(`/contests/${contestId}`, { db: withTeams([]) });
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
    const from = '/explore?category=education';
    const params = new URLSearchParams({ from, teamPage: '2' });
    const contestPath = `/contests/${demoIds.contests.campus}?${params}`;
    const { user, step } = await renderExplore(contestPath, {
      db: withTeams(pagedSeeds, [demoIds.teams.greenwave]),
    });
    const teamSection = screen.getByRole('region', { name: '함께할 팀' });
    expect(
      within(teamSection)
        .getAllByRole('heading', { level: 3 })
        .map((node) => node.textContent),
    ).toEqual(pagedNames.slice(6, 12));
    expect(
      within(teamSection).getByRole('navigation', {
        name: '공모전 팀 목록 페이지',
      }),
    ).toHaveAccessibleDescription('전체 3페이지 중 2페이지');
    expect(screen.getByRole('link', { name: '탐색으로' })).toHaveAttribute(
      'href',
      from,
    );
    await step(() =>
      user.click(
        within(teamSection).getByRole('link', { name: /페이지 팀 07/ }),
      ),
    );
    expect(screen.getByRole('link', { name: '목록으로' })).toHaveAttribute(
      'href',
      contestPath,
    );
    await step(() =>
      user.click(screen.getByRole('link', { name: '목록으로' })),
    );
    expect(currentUrl().searchParams.get('teamPage')).toBe('2');
    expect(currentUrl().searchParams.get('from')).toBe(from);
    expect(
      screen.getByRole('heading', { name: '페이지 팀 07' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: '페이지 팀 01' }),
    ).not.toBeInTheDocument();
  });

  it('preserves the existing local team under official capacity rules without a preparation exception', async () => {
    await renderExplore(`/contests/${demoIds.contests.local}`);
    expect(screen.getByText('2~3명')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '팀 만들기' })).toHaveAttribute(
      'href',
      `/teams/new?contest=${demoIds.contests.local}`,
    );
    expect(screen.queryByText('개인 참가')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /로컬 크루/ })).toBeInTheDocument();
  });

  it('counts every linked team including full and closed teams', async () => {
    await renderExplore('/explore');
    const local = screen.getByRole('link', { name: /우리 동네를 새롭게/ });
    expect(local).toHaveTextContent('연결된 팀 1개');
  });

  it('applies recruitment filters to capacity and dates as well as raw team state', async () => {
    await renderExplore('/explore?tab=teams&open=true', {
      db: withTeams([
        { name: '검토 중 지원 가능' },
        { name: '가득 찬 팀', capacity: '2', members: 2 },
        {
          name: '기한 지난 팀',
          recruitmentEndsAt: '2026-10-17T15:00:00Z',
        },
        { name: '시작 전 팀', contestId: demoIds.contests.upcoming },
      ]),
    });
    expect(
      screen.getByRole('heading', { name: '검토 중 지원 가능' }),
    ).toBeInTheDocument();
    for (const name of ['가득 찬 팀', '기한 지난 팀', '시작 전 팀'])
      expect(screen.queryByRole('heading', { name })).not.toBeInTheDocument();
  });

  it('shows upcoming public contests without allowing team creation', async () => {
    await renderExplore(`/contests/${demoIds.contests.upcoming}`);
    expect(screen.getByText('접수 예정')).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '팀 만들기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('접수가 시작되면 팀을 만들거나 지원할 수 있어요.'),
    ).toBeInTheDocument();
  });
});
