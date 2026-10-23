/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/applicant-review-state.ts - 지원자 AI 검토 상태 원본
 * 2. docs/specs/team-recruitment.md#recruitment-review - 기존 지원자 검토 결과 확인·재요청, 마감 후에도 허용
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import { createContext } from 'react';

export type ApplicantReviewResult = { label: string; value: string }[];
export const ApplicantReviewContext = createContext<{
  results: Record<string, ApplicantReviewResult>;
  save: (id: string, result: ApplicantReviewResult) => void;
} | null>(null);
