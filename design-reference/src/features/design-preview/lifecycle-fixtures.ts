import { initialApplicants, initialApplications, initialTeams } from './data';
import type { TeamActivity } from './team-state';

/** A review scenario only; no persistence or production seeding contract. */
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
