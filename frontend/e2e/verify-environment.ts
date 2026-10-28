// 실행기 밖의 Playwright가 수동 개발 서버에 쓰기 요청을 보내지 못하게 합니다.
import process from 'node:process';
import type { FullConfig } from '@playwright/test';
import { verifyEnvironment } from './environment-guard';

export default function setup(config: FullConfig): void {
  verifyEnvironment(
    config.projects.map((project) => project.use.baseURL),
    process.env,
  );
}
