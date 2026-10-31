/** 독립 디자인 앱의 평가 표시 타입이며 실제 API 계약을 대신하지 않습니다. */
export type AssessmentInformationStatus = 'sufficient' | 'insufficient';
export type AssessmentSource =
  | 'application.role'
  | 'application.message'
  | 'profile.roleCodes'
  | 'profile.skillCodes'
  | 'profile.experienceState'
  | 'profile.experienceBody'
  | 'profile.weeklyAvailabilityCode'
  | 'profile.introduction'
  | 'profile.courses'
  | 'team.roleCodes'
  | 'team.introduction';
export type AssessmentCriterion = {
  key: 'role' | 'skills' | 'experience' | 'availability';
  score: number | null;
  informationStatus: AssessmentInformationStatus;
  summary: string;
  evidence: { source: AssessmentSource; text: string }[];
};
export type ApplicantAssessment = {
  criteria: AssessmentCriterion[];
  questions: string[];
};
