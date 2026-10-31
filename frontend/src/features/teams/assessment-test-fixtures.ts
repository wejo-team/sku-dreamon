/** 지원자 평가 화면 테스트가 공유하는 작은 구조화 응답입니다. */
import type { ApplicantAssessment } from '@/features/ai/contract';

export const assessmentFixture = (): ApplicantAssessment => ({
  criteria: [
    {
      key: 'role',
      score: 85,
      informationStatus: 'sufficient',
      summary: '희망 역할을 등록했어요.',
      evidence: [{ source: 'profile.roleCodes', text: '기획자' }],
    },
    {
      key: 'skills',
      score: 75,
      informationStatus: 'sufficient',
      summary: '서비스 기획 역량을 등록했어요.',
      evidence: [{ source: 'profile.skillCodes', text: '서비스 기획' }],
    },
    {
      key: 'experience',
      score: null,
      informationStatus: 'insufficient',
      summary: '경험을 입력하지 않아 추가 확인이 필요해요.',
      evidence: [],
    },
    {
      key: 'availability',
      score: null,
      informationStatus: 'insufficient',
      summary: '팀에 배정할 시간은 함께 조율해 주세요.',
      evidence: [
        { source: 'profile.weeklyAvailabilityCode', text: '주 5~10시간' },
      ],
    },
  ],
  questions: ['다른 활동을 포함한 시간인가요?'],
});
