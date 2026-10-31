/** 구조화된 평가 항목을 차트의 한국어 이름으로 연결합니다. */
import type { AssessmentCriterion } from './applicant-assessment-types';

export const criterionKeys = [
  'role',
  'skills',
  'experience',
  'availability',
] as const;
export const criterionLabels: Record<AssessmentCriterion['key'], string> = {
  role: '역할',
  skills: '역량',
  experience: '경험',
  availability: '참여 시간',
};
