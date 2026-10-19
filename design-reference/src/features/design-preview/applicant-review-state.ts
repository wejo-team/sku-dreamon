import { createContext } from 'react';

export type ApplicantReviewResult = { label: string; value: string }[];
export const ApplicantReviewContext = createContext<{
  results: Record<string, ApplicantReviewResult>;
  save: (id: string, result: ApplicantReviewResult) => void;
} | null>(null);
