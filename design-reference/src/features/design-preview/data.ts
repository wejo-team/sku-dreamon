export const previewBase = '/design-preview';
export const previewPath = (path = '') => `${previewBase}${path}`;

export type Contest = {
  id: string;
  title: string;
  organizer: string;
  category: string;
  cover?: string;
  deadline: string;
  days: number;
  audience: string;
  description: string;
  teamCount: number;
  startsAt: string;
  officialUrl: string;
  participation: 'team' | 'individual' | 'both';
  minMembers?: number;
  maxMembers?: number;
  status: 'open' | 'closed';
  deliverables: string[];
  verifiedOn: string;
  interests: string[];
};
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
  kind: 'entry' | 'preparation';
  interests: string[];
  memberProfiles: { id: string; name: string; role: string }[];
};
export type Person = {
  id: string;
  name: string;
  roles: string[];
  interests?: string[];
  intro?: string;
  experience?: string;
};
export type ApplicationStatus =
  '지원완료' | '검토중' | '선발' | '미선발' | '지원취소';
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
export type Profile = {
  name: string;
  academicStatus?: string;
  grade?: string;
  college?: string;
  department?: string;
  major?: string;
  skills: string[];
  experienceState: 'unspecified' | 'none' | 'provided';
  portfolioTitle: string;
  interestOther: string;
  skillOther: string;
  roles: string[];
  interests: string[];
  intro: string;
  experience: string;
  visibility: {
    discoverable: boolean;
    interests: boolean;
    experience: boolean;
    intro: boolean;
  };
  portfolio: string;
  portfolioConsent: boolean;
  availability: string;
};

export function getPublicProfile(profile: Profile, id = 'me'): Person | null {
  if (!profile.visibility.discoverable) return null;
  return {
    id,
    name: profile.name,
    roles: [...profile.roles],
    ...(profile.visibility.interests
      ? { interests: [...profile.interests] }
      : {}),
    ...(profile.visibility.experience &&
    (profile.experience || profile.experienceState === 'none')
      ? {
          experience:
            profile.experienceState === 'none'
              ? '관련 경험 없음'
              : profile.experience,
        }
      : {}),
    ...(profile.visibility.intro && profile.intro
      ? { intro: profile.intro }
      : {}),
  };
}

export const contests: Contest[] = [
  {
    id: 'campus',
    startsAt: '2026-10-01',
    officialUrl: '/design-preview/reference/notices/campus',
    participation: 'team',
    minMembers: 2,
    maxMembers: 5,
    status: 'open',
    deliverables: ['아이디어 제안서 PDF', '발표 자료'],
    verifiedOn: '2026-10-18',
    interests: ['교육', 'IT·기술'],
    cover: '/contest-covers/campus.webp',
    title: '더 나은 캠퍼스 아이디어 공모전',
    organizer: '드림온 운영팀',
    category: '교육',
    deadline: '2026.11.08',
    days: 21,
    audience: '대학생 누구나',
    description:
      '우리가 매일 지나는 캠퍼스를 더 편리하게 만드는 아이디어를 제안해요. 문제 발견부터 해결 방향까지, 다양한 전공의 관점을 모아보세요.',
    teamCount: 3,
  },
  {
    id: 'green',
    startsAt: '2026-10-01',
    officialUrl: '/design-preview/reference/notices/green',
    participation: 'team',
    minMembers: 2,
    maxMembers: 4,
    status: 'open',
    deliverables: ['기획서', '프로토타입 소개 영상'],
    verifiedOn: '2026-10-18',
    interests: ['환경', 'IT·기술'],
    cover: '/contest-covers/green.webp',
    title: '일상 속 그린테크 챌린지',
    organizer: '드림온 운영팀',
    category: 'IT·기술',
    deadline: '2026.10.25',
    days: 7,
    audience: '대학생·대학원생',
    description:
      '일상에서 시작할 수 있는 환경 문제를 찾고, 기술로 해결 방법을 제안해요. 작지만 실현할 수 있는 변화를 함께 만들어보세요.',
    teamCount: 2,
  },
  {
    id: 'local',
    startsAt: '2026-10-01',
    officialUrl: '/design-preview/reference/notices/local',
    participation: 'individual',
    status: 'open',
    deliverables: [],
    verifiedOn: '2026-10-18',
    interests: ['디자인', '사회·문화'],
    cover: '/contest-covers/local.webp',
    title: '우리 동네를 새롭게, 로컬 브랜딩',
    organizer: '드림온 운영팀',
    category: '디자인',
    deadline: '2026.11.15',
    days: 28,
    audience: '대학생 누구나',
    description:
      '지역의 고유한 이야기를 발견하고 새로운 시각으로 표현해요. 브랜드 기획과 시각 디자인을 연결하는 팀을 기다립니다.',
    teamCount: 1,
  },
];
export const initialTeams: Team[] = [
  {
    id: 'makers',
    capacity: 4,
    recruitmentDeadline: '2026-11-05',
    kind: 'entry',
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
    kind: 'entry',
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
    kind: 'preparation',
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
  academicStatus: '',
  grade: '',
  college: '',
  department: '',
  major: '',
  skills: [],
  experienceState: 'unspecified',
  portfolioTitle: '',
  interestOther: '',
  skillOther: '',
  roles: ['기획'],
  interests: ['IT·기술', '교육'],
  intro: '다양한 전공의 사람들과 의미 있는 프로젝트를 완성하고 싶어요.',
  experience: '',
  visibility: {
    discoverable: false,
    interests: false,
    experience: false,
    intro: false,
  },
  portfolio: '',
  portfolioConsent: false,
  availability: '월 18:00~21:00; 목 18:00~21:00',
};
export const roleOptions = [
  '기획',
  '디자인',
  '개발',
  '자료조사',
  '발표',
  '마케팅',
];
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
  '기타',
];

export const initialApplicants: Applicant[] = [
  {
    id: 'app-seoyeon',
    personId: 'seoyeon',
    profile: {
      ...initialProfile,
      name: '김서연',
      roles: ['개발'],
      interests: ['IT·기술', '환경'],
      skills: ['프로그래밍', 'UI/UX'],
      experienceState: 'provided',
      experience: '교내 서비스 프로젝트에서 화면 개발을 담당했어요.',
      intro: '함께 배우며 완성하는 팀을 찾고 있어요.',
      visibility: {
        discoverable: true,
        interests: true,
        experience: true,
        intro: true,
      },
      portfolio: new URL(
        '/design-preview/reference/portfolios/seoyeon',
        globalThis.location?.origin ?? 'http://localhost:5174',
      ).href,
      portfolioTitle: '김서연의 프로젝트',
      portfolioConsent: true,
    },
    teamId: 'greenwave',
    name: '김서연',
    role: '개발',
    interests: ['IT·기술', '환경'],
    message:
      '환경 문제를 해결하는 서비스에 관심이 있어요. 프론트엔드 개발을 맡고, 기획도 함께 고민하고 싶습니다.',
    status: '검토중',
  },
  {
    id: 'app-sua',
    personId: 'sua',
    profile: {
      ...initialProfile,
      name: '정수아',
      roles: ['디자인'],
      interests: ['디자인', '환경'],
      skills: ['UI/UX', '그래픽 디자인'],
      experienceState: 'provided',
      experience: '브랜딩 프로젝트 경험',
      intro: '사용자 관점에서 설계합니다.',
      visibility: {
        discoverable: true,
        interests: true,
        experience: false,
        intro: false,
      },
    },
    teamId: 'greenwave',
    name: '정수아',
    role: '디자인',
    interests: ['디자인', '환경'],
    message:
      '사용자 리서치부터 화면 설계까지 함께하고 싶어요. 환경을 위한 작은 행동을 쉽게 만드는 경험에 관심이 있습니다.',
    status: '검토중',
  },
];

export const initialApplications: Application[] = [
  {
    id: 'application-localcrew',
    personId: 'me',
    teamId: 'localcrew',
    role: '기획',
    status: '선발',
    message: '브랜드 기획을 함께하고 싶어요.',
  },
];

// A closed fixture keeps read-only history reviewable without dating the live examples.
export const archivedContest: Contest = {
  ...contests[0]!,
  id: 'archive',
  title: '지난 캠퍼스 아이디어 공모전',
  startsAt: '2026-08-01',
  deadline: '2026.09.30',
  days: -18,
  status: 'closed',
  officialUrl: '/design-preview/reference/notices/archive',
  teamCount: 0,
};

// Directory and applicant views share one profile's global visibility flags.
export const people: Person[] = [
  getPublicProfile(initialApplicants[0]!.profile!, 'seoyeon')!,
  getPublicProfile(
    {
      ...initialProfile,
      name: '이도윤',
      roles: ['개발'],
      interests: ['IT·기술', '디자인'],
      intro:
        '아이디어를 동작하는 화면으로 만드는 프론트엔드 개발에 관심이 있어요.',
      visibility: {
        discoverable: true,
        interests: true,
        experience: false,
        intro: true,
      },
    },
    'doyun',
  )!,
  getPublicProfile(initialApplicants[1]!.profile!, 'sua')!,
];
