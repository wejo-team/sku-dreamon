// 기본 개발 DB 회귀와 명시적으로 선택한 복제본 혼합 검증을 실행합니다.
import { join } from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const artifacts = process.env.E2E_ARTIFACT_DIR;
const mixedData = process.env.E2E_MIXED_DATA === '1';

export default defineConfig({
  testDir: './e2e',
  testMatch: [
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
  },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'https://localhost:5183',
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
