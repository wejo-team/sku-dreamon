/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/data.ts - 예시 공모전·팀·사람·지원 데이터 원본
 * 2. docs/design/handoff.md - 공고·인물·팀·학사 선택지는 화면 확인용 데이터, 외부 링크는 실제 공고 근거 아님
 * 3. docs/specs/contests.md - 공모전 분야 복수, 참가 대상 4분류, 공식 인원
 * 4. docs/specs/profile-options.md - 관심 분야·희망 역할 선택지(기타 제거)
 * 5. docs/design/assets.md - 커버·마스코트 이미지 경로
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import {
  defaultMascotAvatarId,
  type MascotAvatarId,
} from '@/features/demo/mascot-avatars';

// [출처 3] 공고 예시 타입
export type Contest = {
  id: string;
  title: string;
  organizer: string;
  cover?: string;
  deadline: string;
  audience: string[];
  audienceOriginal: string;
  description: string;
  startsAt: string;
  officialUrl: string;
  memberLimit: 'range' | 'unlimited' | 'unknown';
  deadlineTimeZone?: string;
  startsAtTimeZone?: string;
  minMembers?: number;
  maxMembers?: number;
  deliverables: string[];
  verifiedOn: string;
  interests: string[];
};
// [출처 2] 팀 예시 타입
export type Team = {
  id: string;
  name: string;
  contestId: string;
  summary: string;
  roles: string[];
  status: '모집중' | '지원자검토' | '팀원확정' | '모집마감';
  members: number;
  owner: boolean;
  capacity: number;
  recruitmentDeadline: string;
  interests: string[];
  memberProfiles: { id: string; name: string; role: string }[];
};
// [출처 2] 사람 탐색 예시 타입
export type Person = {
  id: string;
  name: string;
  avatarId?: MascotAvatarId;
  roles: string[];
  interests?: string[];
  intro?: string;
  experience?: string;
  academicStatus?: string;
  grade?: string;
  college?: string;
  department?: string;
  major?: string;
  skills?: string[];
  experienceState?: Profile['experienceState'];
  availability?: string;
  portfolio?: string;
  portfolioTitle?: string;
};
// [출처 2] 지원 상태: 지원완료·검토중·선발·미선발·취소·폐기
export type ApplicationStatus =
  '지원완료' | '검토중' | '선발' | '미선발' | '지원취소' | '폐기';
export type Application = {
  id: string;
  personId?: string;
  teamId: string;
  role: string;
  status: ApplicationStatus;
  message: string;
};
export type Applicant = {
  id: string;
  teamId: string;
  name: string;
  role: string;
  interests: string[];
  message: string;
  status: ApplicationStatus;
  personId: string;
  profile?: Profile;
  overlap?: string;
};
// [출처 4] 프로필 예시 타입
export type Profile = {
  name: string;
  avatarId?: MascotAvatarId;
  academicStatus?: string;
  grade?: string;
  college?: string;
  department?: string;
  major?: string;
  skills: string[];
  experienceState: 'unspecified' | 'none' | 'provided';
  portfolioTitle: string;
  roles: string[];
  interests: string[];
  intro: string;
  experience: string;
  visibility: {
    discoverable: boolean;
  };
  portfolio: string;
  availability: string;
};

export function profileToPerson(profile: Profile, id = 'me'): Person {
  return {
    id,
    name: profile.name,
    avatarId: profile.avatarId ?? defaultMascotAvatarId,
    roles: [...profile.roles],
    interests: [...profile.interests],
    intro: profile.intro,
    experience:
      profile.experienceState === 'none'
        ? '관련 경험 없음'
        : profile.experience,
    experienceState: profile.experienceState,
    academicStatus: profile.academicStatus,
    grade: profile.grade,
    college: profile.college,
    department: profile.department,
    major: profile.major,
    skills: [...profile.skills],
    availability: profile.availability,
    portfolio: /^https?:\/\//i.test(profile.portfolio) ? profile.portfolio : '',
    portfolioTitle: profile.portfolioTitle,
  };
}

// [출처 2] 공개 상태일 때만 사람 탐색에 노출
export function getPublicProfile(profile: Profile, id = 'me'): Person | null {
  return profile.visibility.discoverable ? profileToPerson(profile, id) : null;
}

// [출처 3, 5] 공모전 예시
export const contests: Contest[] = [
  {
    id: 'campus',
    startsAt: '2026-10-01',
    officialUrl: '/reference/notices/campus',
    memberLimit: 'range',
    minMembers: 2,
    maxMembers: 5,
    deliverables: ['아이디어 제안서 PDF', '발표 자료'],
    verifiedOn: '2026-10-18',
    interests: ['교육', 'IT·기술'],
    cover: '/contest-covers/campus.webp',
    title: '더 나은 캠퍼스 아이디어 공모전',
    organizer: '드림온 운영팀',
    deadline: '2026.11.08',
    audience: ['대학생'],
    audienceOriginal: '대학생 누구나',
    description:
      '우리가 매일 지나는 캠퍼스를 더 편리하게 만드는 아이디어를 제안해요. 문제 발견부터 해결 방향까지, 다양한 전공의 관점을 모아보세요.',
  },
  {
    id: 'green',
    startsAt: '2026-10-01',
    officialUrl: '/reference/notices/green',
    memberLimit: 'range',
    minMembers: 2,
    maxMembers: 4,
    deliverables: ['기획서', '프로토타입 소개 영상'],
    verifiedOn: '2026-10-18',
    interests: ['환경', 'IT·기술'],
    cover: '/contest-covers/green.webp',
    title: '일상 속 그린테크 챌린지',
    organizer: '드림온 운영팀',
    deadline: '2026.10.25',
    audience: ['대학생'],
    audienceOriginal: '대학생·대학원생',
    description:
      '일상에서 시작할 수 있는 환경 문제를 찾고, 기술로 해결 방법을 제안해요. 작지만 실현할 수 있는 변화를 함께 만들어보세요.',
  },
  {
    id: 'local',
    startsAt: '2026-10-01',
    officialUrl: '/reference/notices/local',
    memberLimit: 'range',
    minMembers: 2,
    maxMembers: 3,
    deliverables: ['브랜드 제안서', '시각 디자인 시안'],
    verifiedOn: '2026-10-18',
    interests: ['디자인', '사회·문화'],
    title: '우리 동네를 새롭게, 로컬 브랜딩',
    organizer: '드림온 운영팀',
    deadline: '2026.11.15',
    audience: ['대학생'],
    audienceOriginal: '대학생 누구나',
    description:
      '지역의 고유한 이야기를 발견하고 새로운 시각으로 표현해요. 브랜드 기획과 시각 디자인을 연결하는 팀을 기다립니다.',
  },
  {
    id: 'solo',
    title: '한 장으로 전하는 캠퍼스 이야기',
    organizer: '드림온 운영팀',
    startsAt: '2026-10-01',
    deadline: '2026-11-20T18:00:00',
    deadlineTimeZone: 'Asia/Seoul',
    officialUrl: '/reference/notices/solo',
    memberLimit: 'range',
    minMembers: 1,
    maxMembers: 1,
    audience: ['대학생'],
    audienceOriginal: '대학생 개인 참가',
    interests: ['디자인', '미디어·콘텐츠'],
    description: '나만의 시선으로 캠퍼스 이야기를 한 장의 포스터에 담아보세요.',
    deliverables: ['포스터 이미지'],
    verifiedOn: '2026-10-18',
  },
  {
    id: 'open-lab',
    title: '함께 만드는 열린 아이디어 실험실',
    organizer: '드림온 운영팀',
    startsAt: '2026-10-01',
    deadline: '2026-11-25',
    officialUrl: '/reference/notices/open-lab',
    memberLimit: 'unlimited',
    minMembers: 1,
    audience: ['대학생', '일반인'],
    audienceOriginal: '대학생 및 일반인, 팀 인원 상한 없음',
    interests: ['IT·기술', '사회·문화'],
    description:
      '여러 사람의 관점을 모아 일상 속 아이디어를 작은 실험으로 만들어보세요.',
    deliverables: ['프로젝트 소개서'],
    verifiedOn: '2026-10-18',
  },
  {
    id: 'upcoming',
    title: '다음 캠퍼스를 상상하는 공모전',
    organizer: '드림온 운영팀',
    startsAt: '2026-11-01',
    deadline: '2026-12-01',
    officialUrl: '/reference/notices/upcoming',
    memberLimit: 'range',
    minMembers: 2,
    maxMembers: 4,
    audience: ['제한 없음'],
    audienceOriginal: '참가 대상 제한 없음',
    interests: ['교육', '환경'],
    description:
      '더 나은 캠퍼스를 위한 새로운 제안을 기다립니다. 접수 시작 전 공고를 먼저 확인해 보세요.',
    deliverables: ['제안서'],
    verifiedOn: '2026-10-18',
  },
];
export const initialTeams: Team[] = [
  {
    id: 'makers',
    capacity: 4,
    recruitmentDeadline: '2026-11-05',
    interests: ['교육', 'IT·기술'],
    memberProfiles: [
      { id: 'minjun', name: '박민준', role: '팀장 · 기획' },
      { id: 'doyun', name: '이도윤', role: '개발' },
    ],
    name: '캠퍼스 메이커스',
    contestId: 'campus',
    summary:
      '캠퍼스 생활의 작은 불편을 함께 해결할 기획자와 디자이너를 찾고 있어요.',
    roles: ['기획', '디자인'],
    status: '모집중',
    members: 2,
    owner: false,
  },
  {
    id: 'greenwave',
    capacity: 4,
    recruitmentDeadline: '2026-10-24',
    interests: ['환경', 'IT·기술'],
    memberProfiles: [
      { id: 'me', name: '김지우', role: '팀장 · 기획' },
      { id: 'haneul', name: '최하늘', role: '자료조사' },
    ],
    name: '그린웨이브',
    contestId: 'green',
    summary: '환경과 기술 사이, 실행할 수 있는 아이디어를 만드는 팀이에요.',
    roles: ['개발', '디자인'],
    status: '모집중',
    members: 2,
    owner: true,
  },
  {
    id: 'localcrew',
    capacity: 3,
    recruitmentDeadline: '2026-11-10',
    interests: ['디자인', '사회·문화'],
    memberProfiles: [
      { id: 'jiho', name: '서지호', role: '팀장 · 디자인' },
      { id: 'me', name: '김지우', role: '기획' },
      { id: 'yuna', name: '한유나', role: '발표' },
    ],
    name: '로컬 크루',
    contestId: 'local',
    summary: '동네의 이야기를 브랜드로 만드는 프로젝트를 준비하고 있어요.',
    roles: ['기획'],
    status: '모집마감',
    members: 3,
    owner: false,
  },
];
export const initialProfile: Profile = {
  name: '김지우',
  avatarId: defaultMascotAvatarId,
  academicStatus: '',
  grade: '',
  college: '',
  department: '',
  major: '',
  skills: [],
  experienceState: 'unspecified',
  portfolioTitle: '',
  roles: ['기획'],
  interests: ['IT·기술', '교육'],
  intro: '다양한 전공의 사람들과 의미 있는 프로젝트를 완성하고 싶어요.',
  experience: '',
  visibility: {
    discoverable: false,
  },
  portfolio: '',

  availability: '',
};
// [출처 4] 희망 역할 6개, 기타 없음
export const roleOptions = [
  '기획',
  '디자인',
  '개발',
  '자료조사',
  '발표',
  '마케팅',
];
// [출처 4] 공통 관심 분야, 기타 제거
export const interestOptions = [
  'IT·기술',
  '경영·창업',
  '디자인',
  '사회·문화',
  '환경',
  '교육',
  '미디어·콘텐츠',
  '보건·의료',
  '정책',
  '공공',
];

export const initialApplicants: Applicant[] = [
  {
    id: 'app-seoyeon',
    status: '검토중',
    personId: 'seoyeon',
    profile: {
      ...initialProfile,
      name: '김서연',
      avatarId: 'arti',
      roles: ['개발'],
      interests: ['IT·기술', '환경'],
      skills: ['프로그래밍', 'UI/UX'],
      experienceState: 'provided',
      experience: '교내 서비스 프로젝트에서 화면 개발을 담당했어요.',
      intro: '함께 배우며 완성하는 팀을 찾고 있어요.',
      visibility: {
        discoverable: true,
      },
      portfolio: new URL(
        '/reference/portfolios/seoyeon',
        globalThis.location?.origin ?? 'http://localhost:5174',
      ).href,
      portfolioTitle: '김서연의 프로젝트',
    },
    teamId: 'greenwave',
    name: '김서연',
    role: '개발',
    interests: ['IT·기술', '환경'],
    message:
      '환경 문제를 해결하는 서비스에 관심이 있어요. 프론트엔드 개발을 맡고, 기획도 함께 고민하고 싶습니다.',
  },
  {
    id: 'app-sua',
    status: '검토중',
    personId: 'sua',
    profile: {
      ...initialProfile,
      name: '정수아',
      avatarId: 'bart',
      roles: ['디자인'],
      interests: ['디자인', '환경'],
      skills: ['UI/UX', '그래픽 디자인'],
      experienceState: 'provided',
      experience: '브랜딩 프로젝트 경험',
      intro: '사용자 관점에서 설계합니다.',
      visibility: {
        discoverable: true,
      },
    },
    teamId: 'greenwave',
    name: '정수아',
    role: '디자인',
    interests: ['디자인', '환경'],
    message:
      '사용자 리서치부터 화면 설계까지 함께하고 싶어요. 환경을 위한 작은 행동을 쉽게 만드는 경험에 관심이 있습니다.',
  },
];

export const initialApplications: Application[] = [
  {
    id: 'application-localcrew',
    status: '선발',
    personId: 'me',
    teamId: 'localcrew',
    role: '기획',
    message: '브랜드 기획을 함께하고 싶어요.',
  },
];

// A closed fixture keeps read-only history reviewable without dating the live examples.
// [출처 3] 마감 공고 읽기 전용 상세 예시(/contests/archive)
export const archivedContest: Contest = {
  ...contests[0]!,
  id: 'archive',
  title: '지난 캠퍼스 아이디어 공모전',
  startsAt: '2026-08-01',
  deadline: '2026.09.30',
  officialUrl: '/reference/notices/archive',
};

// Directory and applicant views share one profile's global visibility flags.
export const people: Person[] = [
  getPublicProfile(initialApplicants[0]!.profile!, 'seoyeon')!,
  getPublicProfile(
    {
      ...initialProfile,
      name: '이도윤',
      avatarId: 'dmo',
      roles: ['개발'],
      interests: ['IT·기술', '디자인'],
      intro:
        '아이디어를 동작하는 화면으로 만드는 프론트엔드 개발에 관심이 있어요.',
      visibility: {
        discoverable: true,
      },
    },
    'doyun',
  )!,
  getPublicProfile(initialApplicants[1]!.profile!, 'sua')!,
];
