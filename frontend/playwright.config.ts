// 실행기가 검증한 전용 DB·서버에서만 브라우저 검사를 실행합니다.
import { join } from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const artifacts = process.env.E2E_ARTIFACT_DIR;
const mixedData = process.env.E2E_MIXED_DATA === '1';
const aiFixture = process.env.E2E_AI_FIXTURE === '1';

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/verify-environment.ts',
  testMatch: aiFixture
    ? ['ai.spec.ts']
    : [
        'service.spec.ts',
        'browse.spec.ts',
        'lifecycle.spec.ts',
        ...(mixedData ? ['mixed-data.spec.ts'] : []),
      ],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir: artifacts ? join(artifacts, 'test-results') : 'test-results',
  reporter: [
    ['list'],
    [
      'html',
      {
        open: 'never',
        outputFolder: artifacts
          ? join(artifacts, 'report')
          : 'playwright-report',
      },
    ],
    ...(artifacts
      ? [['json', { outputFile: join(artifacts, 'results.json') }] as const]
      : []),
  ],
  metadata: {
    dataset:
      process.env.E2E_DATASET ??
      (mixedData ? 'development-db-copy' : 'configured-db'),
    mixedData,
    aiFixture,
  },
  use: {
    baseURL: process.env.E2E_BASE_URL,
    // 전용 로컬 환경의 자체 서명 인증서. HTTP로 Secure 쿠키를 우회하지 않습니다.
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    {
      name: 'mobile-chromium',
      use: { ...devices['Pixel 7'], viewport: { width: 320, height: 740 } },
    },
  ],
});
