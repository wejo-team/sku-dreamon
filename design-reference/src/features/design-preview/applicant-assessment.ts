/** 고정 시연 점수로 화면을 구성하며 실제 모델의 평가 기준을 대신하지 않습니다. */
import type { Applicant, Person } from './data';
import type { ApplicantAssessment } from './applicant-assessment-types';

export function createApplicantAssessment(
  applicant: Applicant,
  profile: Person,
): ApplicantAssessment {
  const hasExperience =
    profile.experienceState === 'provided' && !!profile.experience?.trim();
  const noExperience = profile.experienceState === 'none';
  return {
    criteria: [
      {
        key: 'role',
        score: applicant.role.trim() ? 85 : null,
        informationStatus: applicant.role.trim()
          ? 'sufficient'
          : 'insufficient',
        summary: profile.roles.includes(applicant.role)
          ? '지원한 역할을 희망 역할에도 등록했어요.'
          : '지원한 역할과 희망 역할을 함께 확인해 주세요.',
        evidence: [
          { source: 'application.role', text: applicant.role },
          ...(profile.roles.length
            ? [
                {
                  source: 'profile.roleCodes' as const,
                  text: profile.roles.join(' · '),
                },
              ]
            : []),
          ...(applicant.message
            ? [
                {
                  source: 'application.message' as const,
                  text: applicant.message,
                },
              ]
            : []),
        ],
      },
      {
        key: 'skills',
        score: profile.skills?.length ? 75 : null,
        informationStatus: profile.skills?.length
          ? 'sufficient'
          : 'insufficient',
        summary: profile.skills?.length
          ? '본인이 등록한 역량을 바탕으로 맡을 업무를 이야기해 보세요.'
          : '등록된 역량이 없어 추가 확인이 필요해요.',
        evidence: profile.skills?.length
          ? [{ source: 'profile.skillCodes', text: profile.skills.join(' · ') }]
          : [],
      },
      {
        key: 'experience',
        score: noExperience ? 20 : hasExperience ? 65 : null,
        informationStatus:
          noExperience || hasExperience ? 'sufficient' : 'insufficient',
        summary: noExperience
          ? '관련 경험 없음으로 등록했어요. 시작할 수 있는 업무 범위를 함께 확인해 주세요.'
          : hasExperience
            ? '등록한 경험에서 맡았던 역할을 함께 살펴보세요.'
            : '관련 경험이 미입력 상태예요.',
        evidence: noExperience
          ? [{ source: 'profile.experienceState', text: '관련 경험 없음' }]
          : hasExperience
            ? [{ source: 'profile.experienceBody', text: profile.experience! }]
            : [],
      },
      {
        key: 'availability',
        // 팀의 시간 요구가 없는 시연 데이터는 참여 시간을 채점하지 않습니다.
        score: null,
        informationStatus: 'insufficient',
        summary: profile.availability
          ? '모든 프로젝트를 합친 자기신고 시간이에요. 팀에 배정할 시간은 함께 조율해 주세요.'
          : '주당 참여 가능 시간이 미입력 상태예요.',
        evidence: profile.availability
          ? [
              {
                source: 'profile.weeklyAvailabilityCode',
                text: profile.availability,
              },
            ]
          : [],
      },
    ],
    questions: ['팀 활동에 실제로 배정할 수 있는 시간은 어느 정도인가요?'],
  };
}
