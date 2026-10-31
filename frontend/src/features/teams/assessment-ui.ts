/** 네 평가 항목의 이름과 점수의 접근성 설명을 일관되게 제공합니다. */
import type { AssessmentCriterion } from '@/features/ai/contract';

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

export function criterionScoreDescription(criterion: AssessmentCriterion) {
  return `${criterionLabels[criterion.key]} ${criterion.score === null ? '정보 부족으로 점수 없음' : `${criterion.score}점`}`;
}
