/// <reference types="node" />
// 다른 Playwright 설정으로 실행해도 공유 fixture가 쓰기 시작 전에 막는지 확인합니다.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { expect, it } from 'vitest';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

it.each(['missing-proof', 'changed-project'])(
  'globalSetup을 뺀 별도 설정의 %s 실행도 fixture에서 차단한다',
  (scenario) => {
    const directory = mkdtempSync(join(tmpdir(), 'wejo-e2e-guard-'));
    try {
      const marker = join(directory, 'test-body-started');
      const config = join(directory, 'custom.config.ts');
      writeFileSync(
        config,
        `export default ${JSON.stringify({
          testDir: directory,
          testMatch: 'probe.spec.ts',
          outputDir: join(directory, 'results'),
          reporter: 'line',
          workers: 1,
          use: { baseURL: 'https://localhost:5183' },
        })};\n`,
      );
      writeFileSync(
        join(directory, 'probe.spec.ts'),
        `import { test } from ${JSON.stringify(join(frontend, 'e2e/support.ts'))};\n` +
          `import { writeFileSync } from 'node:fs';\n` +
          `test('must not enter test body', () => writeFileSync(${JSON.stringify(marker)}, 'entered'));\n`,
      );
      const environment = { ...process.env };
      for (const name of Object.keys(environment)) {
        if (
          name.startsWith('E2E_') ||
          name.startsWith('VITE_API_') ||
          name === 'API_PROXY_TARGET'
        ) {
          delete environment[name];
        }
      }
      if (scenario === 'changed-project') {
        Object.assign(environment, {
          E2E_BASE_URL: 'https://localhost:5185',
          E2E_VERIFIED_BASE_URL: 'https://localhost:5185',
          E2E_VERIFIED_BACKEND_URL: 'http://127.0.0.1:8013',
          API_PROXY_TARGET: 'http://127.0.0.1:8013',
          VITE_API_BASE_URL: '/api/v1',
          VITE_API_MOCK: 'false',
        });
      }
      const result = spawnSync(
        process.execPath,
        [
          join(frontend, 'node_modules/@playwright/test/cli.js'),
          'test',
          '--config',
          config,
        ],
        { cwd: frontend, env: environment, encoding: 'utf8', timeout: 10_000 },
      );
      expect(result.error).toBeUndefined();
      expect(result.status).toBe(1);
      expect(result.stdout + result.stderr).toContain('scripts/run_bugbash.py');
      expect(existsSync(marker)).toBe(false);
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  },
);
