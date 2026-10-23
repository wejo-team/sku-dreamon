/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/lifecycle-fixtures.ts - 팀 수명주기 재현 데이터 원본
 * 2. docs/design/screens.md - 「재현 경로」 scenario=team-lifecycle
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import {
  initialApplicants,
  initialApplications,
  initialTeams,
} from '@/features/demo/data';
import type { TeamActivity } from '@/features/demo/team-state';

/** A review scenario only; no persistence or production seeding contract. */
// [출처 2] 폐기·선발·재개 확인용 초기 상태
export function lifecycleReferenceActivity(): TeamActivity {
  const green = initialTeams.find((team) => team.id === 'greenwave')!;
  const local = initialTeams.find((team) => team.id === 'localcrew')!;
  const discarded = {
    ...initialApplications[0]!,
    id: 'application-discarded-local',
    teamId: 'localstudio',
    status: '폐기' as const,
    message: '지역의 이야기를 함께 발굴하고 싶어요.',
  };
  return {
    teams: [
      ...initialTeams.map((team) =>
        team.id === green.id ? { ...team, status: '모집마감' as const } : team,
      ),
      {
        ...green,
        id: 'greenmakers',
        name: '그린 메이커스',
        owner: false,
        members: 2,
        memberProfiles: [
          { id: 'green-leader', name: '이서준', role: '팀장 · 기획' },
          { id: 'seoyeon', name: '김서연', role: '개발' },
        ],
      },
      {
        ...local,
        id: 'localstudio',
        name: '로컬 스튜디오',
        owner: false,
        members: 1,
        status: '모집중',
        memberProfiles: [
          { id: 'local-leader', name: '이수현', role: '팀장 · 디자인' },
        ],
      },
    ],
    applications: [...initialApplications, discarded],
    applicants: [
      ...initialApplicants.map((applicant) =>
        applicant.id === 'app-seoyeon'
          ? { ...applicant, status: '폐기' as const }
          : applicant,
      ),
      {
        ...initialApplicants[0]!,
        id: 'app-greenmakers-seoyeon',
        teamId: 'greenmakers',
        status: '선발',
      },
      { ...discarded, personId: 'me', name: '김지우', interests: [] },
    ],
  };
}
