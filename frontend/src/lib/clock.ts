/**
 * [참조 출처]
 * 1. docs/design/handoff.md - 재현용 예시 데이터는 고정 날짜 기준(운영 시계 아님)
 * 2. docs/development/local-development.md - 프론트 환경변수(VITE_API_MOCK 등)
 *
 * 요청 대상(목업·실서버)과 화면이 쓰는 현재 시각을 정합니다.
 * 목업 데이터는 2026-10-18 기준으로 만든 것이라, 목업 모드와 테스트에서는 같은 고정 시각을 씁니다.
 */

// [출처 2] 지정하지 않으면 개발 서버는 목업, 운영 빌드는 실서버
export const isMockApi =
  (import.meta.env.VITE_API_MOCK ??
    (import.meta.env.DEV ? 'true' : 'false')) === 'true';

// [출처 1] 목업 데이터의 기준 시각
export const MOCK_NOW = Date.parse('2026-10-18T09:00:00Z');

/** 화면 계산용 현재 시각. 목업 응답·테스트는 목업 기준 시각, 실서버는 실제 시각 */
export const appNow = () =>
  isMockApi || import.meta.env.MODE === 'test' ? MOCK_NOW : Date.now();
