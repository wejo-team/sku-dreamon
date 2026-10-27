// 검증한 개발 DB 복제본에서 실제·시연 계정과 팀의 교차 흐름을 확인합니다.
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import type { BrowserContext } from '@playwright/test';
import {
  baseURL,
  createAccount,
  createTeam,
  expect,
  get,
  login,
  selectContest,
  test,
  write,
  type Application,
  type Data,
  type Team,
} from './support';

type SeedAccount = { accountId: string; loginId: string };
type Manifest = {
  database: string;
  checkedAt: string;
  contestId: string;
  demoAccounts: [SeedAccount, SeedAccount];
  team?: {
    id: string;
    name: string;
    memberCount: number;
    capacity: string;
    recruitmentClosesAt: string;
    leader: SeedAccount;
  };
};
type MixedTeam = Team & { name: string; isDemo: boolean };
type MixedProfile = { accountId: string; isDemo: boolean };
type Space = {
  team: MixedTeam;
  viewerRole: 'leader' | 'member';
  members: { accountId: string; isDemo: boolean }[];
};

const seedPassword = 'WejoDev2026!Demo';
const execute = promisify(execFile);

async function prepareCandidates(contestId?: string): Promise<Manifest> {
  const { stdout } = await execute(
    'uv',
    [
      'run',
      '--locked',
      'python',
      '-m',
      'scripts.prepare_mixed_e2e',
      ...(contestId ? ['--contest-id', contestId] : []),
    ],
    {
      cwd: fileURLToPath(new URL('../../backend', import.meta.url)),
      env: process.env,
      timeout: 30_000,
    },
  );
  return JSON.parse(stdout) as Manifest;
}

// 기본 E2E에서 기존 시연 데이터를 변경하지 않는다. runner는 서버 DB와 이
// 읽기 전용 후보 조회 DB가 같은 *_e2e 복제본인지 확인한 뒤 opt-in한다.
if (process.env.E2E_MIXED_DATA === '1') {
  test.beforeAll(() => {
    if (process.env.E2E_MIXED_VERIFIED_BASE_URL !== baseURL) {
      throw new Error(
        '혼합 검사는 DB 대상을 검증하는 scripts/run_bugbash.py로 실행하세요.',
      );
    }
  });
  for (const applicantDemo of [false, true]) {
    for (const teamDemo of [false, true]) {
      test(`${applicantDemo ? '시연' : '실제'} 계정→${teamDemo ? '시연' : '실제'} 팀 지원·선발·결과·접근 권한`, async ({
        browser,
        resources,
      }, testInfo) => {
        test.setTimeout(120_000);
        const contexts: BrowserContext[] = [];
        try {
          const context = async () => {
            const value = await browser.newContext({
              ...testInfo.project.use,
              baseURL,
              ignoreHTTPSErrors: true,
            });
            contexts.push(value);
            return value;
          };
          const leaderContext = await context();
          const applicantContext = await context();
          const outsiderContext = await context();
          const contest = teamDemo
            ? null
            : await selectContest(leaderContext.request, resources);
          const manifest = await prepareCandidates(contest?.id);
          await testInfo.attach('mixed-candidates.json', {
            body: Buffer.from(JSON.stringify(manifest, null, 2)),
            contentType: 'application/json',
          });
          await resources.referenced('contest', manifest.contestId);
          const ownerPage = await leaderContext.newPage();
          const memberPage = await applicantContext.newPage();
          let team: MixedTeam;
          if (teamDemo) {
            expect(manifest.team, '적격 시연 팀이 필요합니다.').toBeDefined();
            const seed = manifest.team!;
            await resources.referenced('team', seed.id);
            await resources.referenced('account', seed.leader.accountId);
            await login(ownerPage, seed.leader.loginId, seedPassword);
            team = (
              await get<Data<MixedTeam>>(
                leaderContext.request,
                `/teams/${seed.id}`,
              )
            ).data;
          } else {
            await createAccount(leaderContext.request, resources);
            team = (await createTeam(
              leaderContext.request,
              contest!,
              resources,
            )) as MixedTeam;
          }
          let applicant: SeedAccount;
          if (applicantDemo) {
            applicant = manifest.demoAccounts[0];
            await resources.referenced('account', applicant.accountId);
            await login(memberPage, applicant.loginId, seedPassword);
          } else {
            applicant = await createAccount(
              applicantContext.request,
              resources,
              true,
            );
          }
          const outsider = manifest.demoAccounts[1];
          await resources.referenced('account', outsider.accountId, {
            role: 'outsider',
          });
          expect(
            (
              await write(outsiderContext.request, 'POST', '/auth/login', {
                loginId: outsider.loginId,
                password: seedPassword,
              })
            ).status(),
          ).toBe(200);
          const profile = (
            await get<Data<MixedProfile>>(
              applicantContext.request,
              '/me/profile',
            )
          ).data;
          expect(profile.accountId).toBe(applicant.accountId);
          expect(profile.isDemo).toBe(applicantDemo);
          expect(team.isDemo).toBe(teamDemo);
          expect(
            (
              await applicantContext.request.get(
                `/api/v1/teams/${team.id}/space`,
              )
            ).status(),
          ).toBe(403);
          expect(
            (
              await outsiderContext.request.get(
                `/api/v1/teams/${team.id}/space`,
              )
            ).status(),
          ).toBe(403);

          await memberPage.goto(`/teams/${team.id}`);
          await expect(
            memberPage.getByRole('heading', { name: team.name, exact: true }),
          ).toBeVisible();
          await memberPage
            .getByRole('radio', { name: '디자인', exact: true })
            .check();
          await memberPage
            .getByLabel(/팀에 전할 말/)
            .fill(`혼합 데이터 검증 ${resources.runId}`);
          const submission = memberPage.waitForResponse(
            (value) =>
              value.url().endsWith(`/teams/${team.id}/applications`) &&
              value.request().method() === 'POST',
          );
          await memberPage
            .getByRole('button', { name: '이 팀에 지원하기' })
            .click();
          const submitted = await submission;
          expect(submitted.status()).toBe(201);
          const application: Application = (await submitted.json()).data;
          await resources.created('application', application.id, {
            teamId: team.id,
            applicantId: applicant.accountId,
          });
          await expect(
            memberPage.getByText('지원이 완료됐어요', { exact: true }),
          ).toBeVisible();
          const review = await get<Data<{ profile: MixedProfile }>>(
            leaderContext.request,
            `/applications/${application.id}/applicant`,
          );
          expect(review.data.profile.isDemo).toBe(applicantDemo);
          await ownerPage.goto(`/applicants/${application.id}`);
          await ownerPage
            .getByRole('button', { name: '이 지원자 선발하기' })
            .click();
          await ownerPage
            .getByRole('button', { name: '선발하고 팀원 확정' })
            .click();
          await expect(
            ownerPage.getByText(/님이 팀원으로 확정됐어요/),
          ).toBeVisible();
          const result = (
            await get<Data<Application>>(
              applicantContext.request,
              `/applications/${application.id}`,
            )
          ).data;
          expect(result.status).toBe('selected');
          const space = (
            await get<Data<Space>>(
              applicantContext.request,
              `/teams/${team.id}/space`,
            )
          ).data;
          expect(space.viewerRole).toBe('member');
          expect(space.team.isDemo).toBe(teamDemo);
          expect(
            space.members.find(
              (member) => member.accountId === applicant.accountId,
            )?.isDemo,
          ).toBe(applicantDemo);
          expect(
            (
              await outsiderContext.request.get(
                `/api/v1/teams/${team.id}/space`,
              )
            ).status(),
          ).toBe(403);
          await memberPage.goto(`/teams/${team.id}?view=space`);
          await expect(
            memberPage.getByRole('heading', { name: '확정된 팀원' }),
          ).toBeVisible();
          await memberPage.screenshot({
            path: testInfo.outputPath('mixed-selected-member.png'),
            fullPage: true,
          });
          expect(
            await memberPage.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth + 1,
            ),
          ).toBe(true);

          // 복제본의 기존 시연 팀 여석을 반환하며 권한도 즉시 회수되는지 확인한다.
          const cancellation = await write(
            applicantContext.request,
            'PUT',
            `/applications/${application.id}/cancellation`,
            { expectedVersion: result.version },
          );
          expect(cancellation.status()).toBe(200);
          expect((await cancellation.json()).data.membershipEnded).toBe(true);
          expect(
            (
              await applicantContext.request.get(
                `/api/v1/teams/${team.id}/space`,
              )
            ).status(),
          ).toBe(403);
          await memberPage.reload();
          await expect(
            memberPage.getByRole('heading', {
              name: '현재 팀원만 팀 공간에 들어갈 수 있어요',
            }),
          ).toBeVisible();
          if (teamDemo) {
            const after = (
              await get<Data<MixedTeam>>(
                leaderContext.request,
                `/teams/${team.id}`,
              )
            ).data;
            expect(after.memberCount).toBe(manifest.team!.memberCount);
            expect(after.recruitmentState).toBe('open');
          }
        } finally {
          await Promise.all(contexts.map((context) => context.close()));
        }
      });
    }
  }
}
