// 기존 개발 DB를 수정하지 않고 실제 탐색 화면과 API 결과를 대조합니다.
import process from 'node:process';
import type { Page } from '@playwright/test';
import type {
  ContestDetail,
  ContestSummary,
} from '../src/features/contests/api';
import {
  test,
  expect,
  get as api,
  login,
  expectDemoBadge,
  captureLayout,
  type Data,
  type Listing as PageResult,
  type Profile,
} from './support';

type Item = {
  id?: string;
  accountId?: string;
  title?: string;
  name?: string;
  realName?: string;
  fieldCodes?: string[];
  isRecruiting?: boolean;
  isDemo: boolean;
};
type Listing = {
  data: Item[];
  pagination: {
    total: number;
    page: number;
    pageSize: number;
    totalPages: number;
  };
};

async function assertListing(
  page: Page,
  kind: 'contests' | 'teams' | 'people',
  expected: Listing,
) {
  const grid = page.locator(`.preview-explore-grid--${kind}`);
  await expect(grid.locator(':scope > a')).toHaveCount(expected.data.length);
  await expect(page.locator('.preview-result-count')).toHaveText(
    `검색 결과 ${expected.pagination.total}개`,
  );
  for (const item of expected.data) {
    const id = item.id ?? item.accountId;
    const card = grid.locator(`a[href^="/${kind}/${id}?"]`);
    await expect(card).toBeVisible();
    await expect(card.getByRole('heading', { level: 3 })).toHaveText(
      item.title ?? item.name ?? item.realName ?? '',
    );
    await expectDemoBadge(
      card,
      kind === 'people' ? 'account' : kind === 'contests' ? 'contest' : 'team',
      item.isDemo,
    );
    if (item.isDemo)
      await expect(card).toHaveAccessibleName(/시연 (계정|공고|팀)/);
  }
  const navigation = page.getByRole('navigation', { name: '탐색 결과 페이지' });
  if (expected.pagination.total === 0) {
    await expect(navigation).toHaveCount(0);
    return;
  }
  const active = navigation.locator('[aria-current="page"]');
  await expect(active).toHaveAttribute(
    'aria-label',
    `${expected.pagination.page}페이지`,
  );
}

test('기존 공고: API 대조·검색·필터·정렬·상세 복귀·빈 결과·페이지 경계', async ({
  page,
  resources,
}, testInfo) => {
  test.setTimeout(120_000);
  const first = await api<Listing>(
    page.request,
    '/contests?page=1&pageSize=6&sort=created_desc',
  );
  expect(
    first.pagination.totalPages,
    '페이지 이동을 검증할 기존 공고가 필요합니다',
  ).toBeGreaterThan(1);
  await page.goto('/explore');
  await assertListing(page, 'contests', first);
  await captureLayout(page, testInfo, 'demo-contest-list');

  const second = await api<Listing>(
    page.request,
    '/contests?page=2&pageSize=6&sort=created_desc',
  );
  await page
    .getByRole('navigation', { name: '탐색 결과 페이지' })
    .getByRole('link', { name: '다음 페이지' })
    .click();
  await expect(page).toHaveURL(/page=2/);
  await assertListing(page, 'contests', second);
  expect(second.data.map((item) => item.id)).not.toEqual(
    first.data.map((item) => item.id),
  );

  const query = first.data[0].title!;
  await page.getByRole('textbox', { name: '탐색 검색' }).fill(query);
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get('q') === query && !url.searchParams.has('page'),
  );
  const searched = await api<Listing>(
    page.request,
    `/contests?q=${encodeURIComponent(query)}&page=1&pageSize=6&sort=created_desc`,
  );
  expect(searched.data.some((item) => item.id === first.data[0].id)).toBe(true);
  await assertListing(page, 'contests', searched);

  await page.getByRole('button', { name: '검색어 지우기' }).click();
  await assertListing(page, 'contests', first);
  const fields = await api<{
    data: { fields: { code: string; displayName: string }[] };
  }>(page.request, '/catalogs');
  const fieldCode = first.data.find((item) => item.fieldCodes?.length)
    ?.fieldCodes?.[0];
  expect(fieldCode).toBeTruthy();
  const field = fields.data.fields.find((item) => item.code === fieldCode)!;
  await page.getByRole('button', { name: '탐색 필터', exact: true }).click();
  await page
    .getByRole('radio', { name: field.displayName, exact: true })
    .check();
  await page.getByRole('button', { name: '취소', exact: true }).click();
  await expect(page).not.toHaveURL(/category=/);
  await assertListing(page, 'contests', first);
  await page.getByRole('button', { name: '탐색 필터', exact: true }).click();
  await expect(
    page.getByRole('radio', { name: '모든 분야', exact: true }),
  ).toBeChecked();
  await page
    .getByRole('radio', { name: field.displayName, exact: true })
    .check();
  await page.getByRole('button', { name: '필터 적용', exact: true }).click();
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('category') === field.code,
  );
  const filtered = await api<Listing>(
    page.request,
    `/contests?fieldCode=${encodeURIComponent(field.code)}&page=1&pageSize=6&sort=created_desc`,
  );
  expect(
    filtered.data.every((item) => item.fieldCodes?.includes(field.code)),
  ).toBe(true);
  await assertListing(page, 'contests', filtered);
  await page
    .getByRole('combobox', { name: '정렬', exact: true })
    .selectOption('deadline');
  const sorted = await api<Listing>(
    page.request,
    `/contests?fieldCode=${encodeURIComponent(field.code)}&page=1&pageSize=6&sort=deadline_asc`,
  );
  await assertListing(page, 'contests', sorted);
  const listUrl = page.url();
  const selected = sorted.data[0];
  const detail = await api<{ data: Item }>(
    page.request,
    `/contests/${selected.id}`,
  );
  expect(detail.data.title).toBe(selected.title);
  await page
    .locator(
      `.preview-explore-grid--contests a[href^="/contests/${selected.id}?"]`,
    )
    .click();
  await expect(
    page.getByRole('heading', { level: 1, name: selected.title!, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: '공모전 소개', exact: true }),
  ).toBeVisible();
  await expectDemoBadge(
    page.locator('.preview-detail-grid article'),
    'contest',
    detail.data.isDemo,
  );
  await captureLayout(page, testInfo, 'devdb-contest-detail');
  await page.getByRole('link', { name: '탐색으로', exact: true }).click();
  await expect(page).toHaveURL(listUrl);
  await assertListing(page, 'contests', sorted);
  await resources.referenced('contest', selected.id!, {
    title: selected.title,
  });
  await page
    .getByRole('button', { name: '검색 조건 초기화', exact: true })
    .click();
  await expect(page).toHaveURL(/\/explore$/);
  await assertListing(page, 'contests', first);
  const missingQuery = `없는공고${resources.runId}`;
  await page.getByRole('textbox', { name: '탐색 검색' }).fill(missingQuery);
  const empty = await api<Listing>(
    page.request,
    `/contests?q=${missingQuery}&page=1&pageSize=6&sort=created_desc`,
  );
  expect(empty.pagination.total).toBe(0);
  await assertListing(page, 'contests', empty);
  await page.goto('/explore?page=invalid');
  await expect(page).toHaveURL(/\/explore$/);
  await assertListing(page, 'contests', first);
  const last = await api<Listing>(
    page.request,
    `/contests?page=${first.pagination.totalPages}&pageSize=6&sort=created_desc`,
  );
  await page.goto(`/explore?page=${first.pagination.totalPages + 10}`);
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('page') === String(last.pagination.page),
  );
  await assertListing(page, 'contests', last);
  await expect(
    page
      .getByRole('navigation', { name: '탐색 결과 페이지' })
      .getByRole('button', { name: '다음 페이지' }),
  ).toBeDisabled();
  await page.screenshot({
    path: testInfo.outputPath('devdb-contest-last-page.png'),
    fullPage: true,
  });
  await testInfo.attach('existing-contest-count', {
    body: JSON.stringify({
      total: first.pagination.total,
      pageSize: first.pagination.pageSize,
      totalPages: first.pagination.totalPages,
    }),
    contentType: 'application/json',
  });
});

test('기존 시드 로그인: 팀·사람 탐색과 페이지·상세 조회, 프로필 보존', async ({
  page,
  resources,
}, testInfo) => {
  test.setTimeout(120_000);
  await login(
    page,
    process.env.E2E_DEMO_LOGIN_ID ?? 'devuser001',
    process.env.E2E_DEMO_PASSWORD ?? 'WejoDev2026!Demo',
  );
  const before = await api<Data<Profile>>(page.request, '/me/profile');
  expect(before.data.isDemo).toBe(true);
  await resources.referenced('account', before.data.accountId, {
    isDemo: true,
  });
  await expect(
    page.getByRole('heading', {
      level: 2,
      name: before.data.realName,
      exact: true,
    }),
  ).toBeVisible();

  await expectDemoBadge(
    page.getByRole('region', { name: '내 기본 정보' }),
    'account',
    before.data.isDemo,
  );
  await expect(
    page.getByRole('button', { name: '교내 미인증, 학교 인증 안내' }),
  ).toBeVisible();
  await captureLayout(page, testInfo, 'demo-own-profile');

  const teams = await api<Listing>(page.request, '/teams?page=1&pageSize=6');
  expect(
    teams.pagination.totalPages,
    '페이지 이동을 검증할 기존 팀이 필요합니다',
  ).toBeGreaterThan(1);
  await page.goto('/explore?tab=teams');
  await assertListing(page, 'teams', teams);
  await captureLayout(page, testInfo, 'demo-team-list');
  await page
    .getByRole('navigation', { name: '탐색 결과 페이지' })
    .getByRole('link', { name: '다음 페이지' })
    .click();
  const teamSecond = await api<Listing>(
    page.request,
    '/teams?page=2&pageSize=6',
  );
  await assertListing(page, 'teams', teamSecond);
  await page.getByRole('button', { name: '탐색 필터', exact: true }).click();
  await page.getByRole('checkbox', { name: '모집중만', exact: true }).check();
  await page.getByRole('button', { name: '필터 적용', exact: true }).click();
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get('open') === 'true' && !url.searchParams.has('page'),
  );
  const recruiting = await api<Listing>(
    page.request,
    '/teams?recruitingOnly=true&page=1&pageSize=6',
  );
  expect(recruiting.data.length).toBeGreaterThan(0);
  expect(recruiting.data.every((item) => item.isRecruiting)).toBe(true);
  await assertListing(page, 'teams', recruiting);

  const teamUrl = page.url();
  const selectedTeam = recruiting.data[0];
  const teamDetail = await api<Data<Item>>(
    page.request,
    `/teams/${selectedTeam.id}`,
  );
  await page
    .locator(
      `.preview-explore-grid--teams a[href^="/teams/${selectedTeam.id}?"]`,
    )
    .click();
  await expect(
    page.getByRole('heading', { name: selectedTeam.name!, exact: true }),
  ).toBeVisible();
  await expectDemoBadge(page, 'team', teamDetail.data.isDemo);
  await captureLayout(page, testInfo, 'demo-team-detail');
  await page.goto(teamUrl);

  const people = await api<Listing>(page.request, '/people?page=1&pageSize=6');
  expect(
    people.pagination.totalPages,
    '페이지 이동을 검증할 공개 프로필이 필요합니다',
  ).toBeGreaterThan(1);
  await page.goto('/explore?tab=people');
  await assertListing(page, 'people', people);
  await captureLayout(page, testInfo, 'demo-person-list');
  await page
    .getByRole('navigation', { name: '탐색 결과 페이지' })
    .getByRole('link', { name: '다음 페이지' })
    .click();
  const peopleSecond = await api<Listing>(
    page.request,
    '/people?page=2&pageSize=6',
  );
  await assertListing(page, 'people', peopleSecond);
  const listUrl = page.url();
  const selected = peopleSecond.data[0];
  await page
    .locator(
      `.preview-explore-grid--people a[href^="/people/${selected.accountId}?"]`,
    )
    .click();
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: selected.realName!,
      exact: true,
    }),
  ).toBeVisible();
  const personDetail = await api<Data<Profile>>(
    page.request,
    `/people/${selected.accountId}`,
  );
  await expectDemoBadge(page, 'account', personDetail.data.isDemo);
  await captureLayout(page, testInfo, 'demo-person-detail');
  await page.getByRole('link', { name: '사람 탐색으로', exact: true }).click();
  await expect(page).toHaveURL(listUrl);
  await assertListing(page, 'people', peopleSecond);
  const after = await api<Data<Profile>>(page.request, '/me/profile');
  expect(after.data).toEqual(before.data);
  await page.screenshot({
    path: testInfo.outputPath('devdb-people-page2.png'),
    fullPage: true,
  });
  await testInfo.attach('existing-directory-counts', {
    body: JSON.stringify({
      teams: teams.pagination.total,
      people: people.pagination.total,
    }),
    contentType: 'application/json',
  });
});

test('실제 공고의 미확인 출처·시작 시각 보완·마감 상세', async ({
  page,
  resources,
}) => {
  test.setTimeout(120_000);
  const samples = new Map<string, ContestDetail>();
  for (let current = 1; samples.size < 3; current += 1) {
    const listing = await api<PageResult<ContestSummary>>(
      page.request,
      `/contests?page=${current}&pageSize=100`,
    );
    for (const summary of listing.data) {
      const { data: detail } = await api<Data<ContestDetail>>(
        page.request,
        `/contests/${summary.id}`,
      );
      if (detail.verifiedAt === null) samples.set('unverified', detail);
      if (detail.officialUrl === null) samples.set('collected', detail);
      if (detail.timing.openTimeDefaulted) samples.set('defaulted', detail);
      if (samples.size === 3) break;
    }
    if (current >= listing.pagination.totalPages) break;
  }
  expect(
    [...samples.keys()].sort(),
    '기존 공고에서 계약 회귀에 필요한 세 사례를 찾지 못했습니다',
  ).toEqual(['collected', 'defaulted', 'unverified']);
  const closed = await api<PageResult<ContestSummary>>(
    page.request,
    '/contests?registrationStatus=closed&pageSize=1',
  );
  expect(
    closed.data.length,
    '마감 공고 직접 열람을 검증할 기존 공고가 필요합니다',
  ).toBe(1);
  const { data: archived } = await api<Data<ContestDetail>>(
    page.request,
    `/contests/${closed.data[0].id}`,
  );
  samples.set('closed', archived);
  for (const [kind, detail] of samples) {
    await resources.referenced('contest', detail.id, { kind });
    await page.goto(`/contests/${detail.id}`);
    await expect(
      page.getByRole('heading', { level: 1, name: detail.title, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('link', {
        name: detail.officialUrl ? '공식 공고 확인하기' : '수집 출처 확인하기',
        exact: true,
      }),
    ).toHaveAttribute('href', detail.officialUrl ?? detail.sourceUrl);
    if (detail.verifiedAt === null)
      await expect(
        page.getByText('공식 원문 미확인', { exact: true }),
      ).toBeVisible();
    if (detail.timing.openTimeDefaulted)
      await expect(
        page.getByText(/원문에 접수 시작 시각이 없어/),
      ).toBeVisible();
    if (kind === 'closed')
      await expect(
        page
          .locator('article > .preview-row')
          .getByText('접수 마감', { exact: true }),
      ).toBeVisible();
  }
});
