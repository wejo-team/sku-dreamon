const { chromium } = require(
  process.env.PLAYWRIGHT_MODULE || '@playwright/test',
);
const assert = require('node:assert/strict');
const { mkdir } = require('node:fs/promises');
const path = require('node:path');

const base = process.env.BASE_URL || 'http://127.0.0.1:5174';
const output = process.env.SCREENSHOT_DIR || path.resolve('screenshotqa');
async function ready(page) {
  // Let route commits and Drawer transitions settle before capturing the visual reference.
  await page.waitForTimeout(400);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      [...document.images].map((image) => image.decode().catch(() => {})),
    );
    await new Promise((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(resolve)),
    );
  });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    'Horizontal overflow',
  );
}
async function snapshot(page, name) {
  await ready(page);
  await page.screenshot({
    path: path.join(output, `${name}.png`),
    animations: 'disabled',
  });
}
async function login(page, returnTo = '/design-preview/explore') {
  await page.goto(
    `${base}/design-preview/login?returnTo=${encodeURIComponent(returnTo)}`,
  );
  await page.getByLabel('아이디', { exact: true }).fill('dreamon-demo');
  await page.getByLabel('비밀번호', { exact: true }).fill('dreamon-demo');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page.waitForURL(`**${returnTo}`);
}
async function navigate(page, route) {
  // Browser history navigation preserves the mounted session, like an in-app Link.
  await page.evaluate((route) => {
    history.pushState({}, '', route);
    dispatchEvent(new PopStateEvent('popstate'));
  }, route);
}
(async () => {
  await mkdir(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
  });
  try {
    for (const width of [320, 390, 430]) {
      const page = await browser.newPage({ viewport: { width, height: 844 } });
      page.setDefaultTimeout(10000);
      const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await page.goto(`${base}/design-preview/explore?tab=people`);
      await page
        .getByRole('heading', { name: '로그인하고 함께할 사람을 찾아보세요' })
        .waitFor();
      assert.equal(await page.locator('a[href*="/people/"]').count(), 0);
      await page.goto(`${base}/design-preview/contests/archive`);
      await page
        .locator('[data-slot=badge]')
        .filter({ hasText: '접수 마감' })
        .waitFor();
      assert.equal(
        await page
          .getByRole('link', { name: '팀 만들기', exact: true })
          .count(),
        0,
      );
      await login(page);
      await snapshot(page, `explore-${width}`);
      await navigate(page, '/design-preview/teams/new?contest=campus');
      await page.getByLabel('팀장 포함 총 정원').waitFor();
      await snapshot(page, `create-team-${width}`);
      await navigate(page, '/design-preview/profile');
      await page
        .getByRole('button', { name: '프로필 수정', exact: true })
        .click();
      assert.equal(
        await page
          .getByRole('switch', { name: '사람 탐색에 공개', exact: true })
          .isChecked(),
        false,
      );
      assert.equal(
        await page
          .getByRole('switch', { name: '관심 분야 공개', exact: true })
          .isEnabled(),
        true,
      );
      await snapshot(page, `profile-${width}`);
      await navigate(page, '/design-preview/applicants/app-seoyeon');
      await page.getByRole('button', { name: '이 지원자 선발하기' }).click();
      await page.getByRole('dialog').waitFor();
      await snapshot(page, `selection-${width}`);
      await page
        .getByRole('button', { name: '선발하고 팀원 확정', exact: true })
        .click();
      await page
        .getByText('김서연 님이 팀원으로 확정됐어요', { exact: true })
        .waitFor();
      await page
        .getByRole('link', { name: '팀 공간으로', exact: true })
        .click();
      await page.getByText('김서연', { exact: true }).waitFor();
      await snapshot(page, `members-${width}`);
      await navigate(page, '/design-preview/ai?scenario=error');
      await page
        .getByRole('button', {
          name: '개발자를 모집하는 팀 찾아줘',
          exact: true,
        })
        .click();
      await page
        .getByRole('button', { name: '다시 시도', exact: true })
        .click();
      await page.getByRole('link', { name: /그린웨이브/ }).waitFor();
      await snapshot(page, `ai-${width}`);
      await navigate(
        page,
        '/design-preview/explore?scenario=notification-error',
      );
      await page.getByRole('button', { name: /^알림/ }).click();
      await page
        .getByRole('button', { name: '모두 읽음', exact: true })
        .click();
      await page
        .getByRole('button', { name: '다시 시도', exact: true })
        .click();
      await page.getByRole('button', { name: /읽지 않음/ }).click();
      await page
        .getByRole('heading', { name: '모든 알림을 확인했어요' })
        .waitFor();
      await snapshot(page, `notifications-${width}`);
      assert.deepEqual(errors, []);
      await page.close();
      console.log(
        `${width}px: guest privacy, closed contest, create/profile, selection/membership, AI retry, notifications passed`,
      );
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
