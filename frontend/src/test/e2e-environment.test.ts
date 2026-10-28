// 브라우저 검사에서 실행기 검증 누락·대상 변경이 시작 전에 차단되는지 확인합니다.
import { describe, expect, it } from 'vitest';
import { verifyEnvironment } from '../../e2e/environment-guard';

const origin = 'https://localhost:5185';
const backend = 'http://127.0.0.1:8013';
const environment = {
  E2E_VERIFIED_BASE_URL: origin,
  E2E_VERIFIED_BACKEND_URL: backend,
  E2E_BASE_URL: origin,
  API_PROXY_TARGET: backend,
  VITE_API_MOCK: 'false',
  VITE_API_BASE_URL: '/api/v1',
};

describe('브라우저 검사 실행 경계', () => {
  it('실행기가 확인한 모든 프로젝트의 주소가 일치해야 실행한다', () => {
    expect(() =>
      verifyEnvironment([origin, origin], environment),
    ).not.toThrow();
  });

  it('검증 없이 기존 개발 서버를 지정한 직접 실행을 거부한다', () => {
    expect(() =>
      verifyEnvironment(['https://localhost:5183'], {
        E2E_BASE_URL: 'https://localhost:5183',
      }),
    ).toThrow('scripts/run_bugbash.py');
  });

  it.each([
    ['E2E_BASE_URL', 'https://localhost:5183'],
    ['E2E_VERIFIED_BASE_URL', undefined],
    ['E2E_VERIFIED_BACKEND_URL', undefined],
    ['API_PROXY_TARGET', 'http://127.0.0.1:8011'],
    ['VITE_API_BASE_URL', 'https://localhost:5183/api/v1'],
    ['VITE_API_MOCK', 'true'],
  ])('%s의 우회 설정을 거부한다', (name, value) => {
    expect(() =>
      verifyEnvironment([origin], { ...environment, [name]: value }),
    ).toThrow('scripts/run_bugbash.py');
  });

  it('개별 프로젝트가 다른 서버를 대상으로 하면 거부한다', () => {
    expect(() =>
      verifyEnvironment([origin, 'https://localhost:5183'], environment),
    ).toThrow('scripts/run_bugbash.py');
  });
});
