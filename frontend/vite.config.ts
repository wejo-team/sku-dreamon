import { readFileSync } from 'node:fs';
import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // 실서버 인증 쿠키는 Secure라 브라우저 검증에 HTTPS가 필요합니다(docs/api/conventions.md#csrf-transport).
  // 로컬 인증서 경로를 지정했을 때만 HTTPS 개발 서버로 띄웁니다.
  const https =
    env.DEV_HTTPS_CERT && env.DEV_HTTPS_KEY
      ? {
          cert: readFileSync(env.DEV_HTTPS_CERT),
          key: readFileSync(env.DEV_HTTPS_KEY),
        }
      : undefined;

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      port: 5173,
      strictPort: true,
      https,
      proxy: {
        '/api': {
          target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      clearMocks: true,
      restoreMocks: true,
      unstubGlobals: true,
      // 테스트는 fetch를 직접 대신하므로 목업 어댑터 전환을 끕니다(화면 테스트는 fetch를 목업으로 연결).
      env: { VITE_API_MOCK: 'false' },
      // 화면 테스트는 폼 입력과 목업 API 요청 흐름 전체를 거치므로 병렬 실행에서 5초 기본값을 넘을 수 있습니다.
      testTimeout: 15_000,
    },
  };
});
