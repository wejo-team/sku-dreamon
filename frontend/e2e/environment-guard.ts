// 검증한 실행 대상과 브라우저 프로젝트·프록시 설정의 일치를 확인합니다.
type Environment = Record<string, string | undefined>;

export function verifyEnvironment(
  baseURLs: (string | undefined)[],
  environment: Environment,
): void {
  const origin = environment.E2E_VERIFIED_BASE_URL;
  const backend = environment.E2E_VERIFIED_BACKEND_URL;
  if (
    !origin ||
    !/^https:\/\/localhost:[0-9]+$/.test(origin) ||
    !backend ||
    !/^http:\/\/127\.0\.0\.1:[0-9]+$/.test(backend) ||
    environment.E2E_BASE_URL !== origin ||
    environment.API_PROXY_TARGET !== backend ||
    environment.VITE_API_MOCK !== 'false' ||
    environment.VITE_API_BASE_URL !== '/api/v1' ||
    !baseURLs.length ||
    baseURLs.some((baseURL) => baseURL !== origin)
  ) {
    throw new Error(
      '브라우저 검사는 격리 DB를 확인하는 scripts/run_bugbash.py로 실행하세요. 직접 npm test:e2e 실행과 대상 주소 변경은 허용하지 않습니다.',
    );
  }
}
