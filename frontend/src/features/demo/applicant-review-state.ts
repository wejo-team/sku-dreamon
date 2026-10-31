/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/applicant-review-state.ts - 지원자 AI 검토 상태 원본
 * 2. docs/specs/team-recruitment.md#recruitment-review - 기존 지원자 검토 결과 확인·재요청, 마감 후에도 허용
 *
 * 제품 mock 화면의 메모리 상태입니다. 실제 API 결과·권한 재검증은 use-target-ai.ts가 별도로 관리합니다.
 */

import { createContext } from 'react';
import type { ApplicantAssessment } from '@/features/ai/contract';

// 등록 사실은 변경 감지에만 사용하고, 화면에는 명시적인 시연 점수를 표시합니다.
export type ApplicantReviewFacts = {
  facts: { label: string; value: string }[];
  assessment: ApplicantAssessment;
};
export const ApplicantReviewContext = createContext<{
  results: Record<string, ApplicantReviewFacts>;
  save: (id: string, result: ApplicantReviewFacts) => void;
} | null>(null);
