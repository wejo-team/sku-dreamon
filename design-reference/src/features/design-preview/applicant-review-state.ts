/** 현재 탭의 로컬 평가 예시를 보관하고 다시 표시합니다. */
import { createContext } from 'react';
import type { ApplicantAssessment } from './applicant-assessment-types';

export type ApplicantReviewResult = {
  facts: { label: string; value: string }[];
  assessment: ApplicantAssessment;
};
export const ApplicantReviewContext = createContext<{
  results: Record<string, ApplicantReviewResult>;
  save: (id: string, result: ApplicantReviewResult) => void;
} | null>(null);
