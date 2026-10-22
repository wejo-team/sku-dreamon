/**
 * [참조 출처]
 * 1. docs/design/screens.md - 공모전, 팀, 사람 탐색 및 워크스페이스 명세
 * 2. docs/design/tokens.md - 파워프렌즈 마스코트 아바타 목록
 * 3. docs/design/assets.md - 공모전 커버 및 캐릭터 에셋 출처
 * 4. docs/development/frontend.md - camelCase 데이터 구조 및 타입 선언 규격
 * 5. design-reference/src/features/design-preview/data.ts - Mock 데이터 및 타입 원본
 */

export type MascotAvatarId = 'skon' | 'arti' | 'dmo' | 'bart' | 'conver';

export const mascotList: { id: MascotAvatarId; name: string; file: string }[] =
  [
    { id: 'skon', name: '스콘 (SKON)', file: '/mascots/skon.png' },
    { id: 'arti', name: '아티 (ARTI)', file: '/mascots/arti.png' },
    { id: 'dmo', name: '디모 (D-MO)', file: '/mascots/dmo.png' },
    { id: 'bart', name: '비아트 (B-ART)', file: '/mascots/bart.png' },
    { id: 'conver', name: '컨버 (CONVER)', file: '/mascots/conver.png' },
  ];

export interface Contest {
  id: string;
  title: string;
  organizer: string;
  cover?: string;
  deadline: string;
  startsAt: string;
  audience: string[];
  audienceOriginal: string;
  description: string;
  officialUrl: string;
  memberLimit: 'range' | 'unlimited' | 'unknown';
  minMembers?: number;
  maxMembers?: number;
  deliverables: string[];
  verifiedOn: string;
  interests: string[];
}

export interface Team {
  id: string;
  name: string;
  contestId: string;
  summary: string;
  roles: string[];
  status: '모집중' | '지원자검토' | '팀원확정' | '모집마감';
  members: number;
  capacity: number;
  owner: boolean;
  recruitmentDeadline: string;
  interests: string[];
  memberProfiles: { id: string; name: string; role: string }[];
}

export interface Person {
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
  availability?: string;
  portfolio?: string;
  portfolioTitle?: string;
  visibility?: { discoverable: boolean };
}

export type ApplicationStatus =
  '지원완료' | '검토중' | '선발' | '미선발' | '지원취소' | '폐기';

export interface Application {
  id: string;
  teamId: string;
  personId?: string;
  role: string;
  status: ApplicationStatus;
  message: string;
  submittedAt?: string;
  discardReason?: string;
}

// [출처 1, 5] 검증된 공모전 예시 데이터
export const mockContests: Contest[] = [
  {
    id: 'campus',
    title: '더 나은 캠퍼스 아이디어 공모전',
    organizer: '드림온 운영팀',
    deadline: '2026.11.08',
    startsAt: '2026-10-01',
    interests: ['교육', 'IT·기술'],
    cover: '/contest-covers/campus.webp',
    audience: ['대학생'],
    audienceOriginal: '대학생 누구나',
    description:
      '우리가 매일 지나는 캠퍼스를 더 편리하게 만드는 아이디어를 제안해요. 문제 발견부터 해결 방향까지, 다양한 전공의 관점을 모아보세요.',
    officialUrl: 'https://www.skuniv.ac.kr',
    memberLimit: 'range',
    minMembers: 2,
    maxMembers: 5,
    deliverables: ['아이디어 제안서 PDF', '발표 자료'],
    verifiedOn: '2026-10-18',
  },
  {
    id: 'green',
    title: '그린웨이브 지속가능 아이디어톤',
    organizer: '녹색전환네트워크',
    deadline: '2026.11.15',
    startsAt: '2026-10-01',
    interests: ['환경', '기획'],
    cover: '/contest-covers/green.webp',
    audience: ['대학생', '일반인'],
    audienceOriginal: '환경에 관심 있는 누구나',
    description:
      '일상 속 자원 낭비를 줄이고 순환 경제를 실천할 아이디어를 찾습니다. 실행 가능한 비즈니스 모델로 발전시켜 보세요.',
    officialUrl: 'https://www.skuniv.ac.kr',
    memberLimit: 'range',
    minMembers: 2,
    maxMembers: 4,
    deliverables: ['기획서', '프로토타입 소개 영상'],
    verifiedOn: '2026-10-18',
  },
  {
    id: 'local',
    title: '로컬 임팩트 메이커톤 2026',
    organizer: '성북 문화도시센터',
    deadline: '2026.11.22',
    startsAt: '2026-10-15',
    interests: ['디자인', '지역·사회'],
    cover: '/contest-covers/skon-default.png',
    audience: ['대학생'],
    audienceOriginal: '성북구 대학생',
    description:
      '지역 상권과 청년을 연결하는 서비스 프로토타입을 제작합니다. 주말 동안 집중 멘토링과 팀 빌딩이 함께 진행됩니다.',
    officialUrl: 'https://www.skuniv.ac.kr',
    memberLimit: 'range',
    minMembers: 3,
    maxMembers: 6,
    deliverables: ['최종 피치덱', '데모 시연 영상'],
    verifiedOn: '2026-10-18',
  },
];

// [출처 1, 5] 검증된 팀 예시 데이터
export const mockTeams: Team[] = [
  {
    id: 'team-greenwave',
    name: '그린웨이브 프로젝트',
    contestId: 'green',
    summary:
      '캠퍼스 내 일회용품 회수함 UX를 재설계하고 학생 참여를 유도하는 리워드 앱 서비스를 기획합니다.',
    roles: ['기획', '디자인', '개발'],
    status: '모집중',
    members: 2,
    capacity: 4,
    owner: true,
    recruitmentDeadline: '2026.11.05',
    interests: ['환경', '기획'],
    memberProfiles: [
      { id: 'me', name: '김서경', role: '팀장' },
      { id: 'seoyeon', name: '이서연', role: '디자이너' },
    ],
  },
  {
    id: 'team-campus1',
    name: '스마트 캠퍼스 지도',
    contestId: 'campus',
    summary:
      '건물별 혼잡도와 강의실 접근성을 시각화하여 신입생과 편입생의 캠퍼스 적응을 돕는 웹 서비스를 만듭니다.',
    roles: ['개발', '데이터분석'],
    status: '모집중',
    members: 3,
    capacity: 5,
    owner: false,
    recruitmentDeadline: '2026.11.02',
    interests: ['교육', 'IT·기술'],
    memberProfiles: [
      { id: 'doyun', name: '박도윤', role: '팀장' },
      { id: 'sua', name: '최수아', role: '기획자' },
      { id: 'minjae', name: '정민재', role: '개발자' },
    ],
  },
  {
    id: 'team-local1',
    name: '성북 청년 공방',
    contestId: 'local',
    summary:
      '성북동 예술가와 청년 창작자를 연결하는 오픈 스튜디오 맵과 클래스 예약 플랫폼을 함께 만들 팀원을 모집합니다.',
    roles: ['마케팅', '디자인'],
    status: '모집마감',
    members: 4,
    capacity: 4,
    owner: false,
    recruitmentDeadline: '2026.10.20',
    interests: ['디자인', '지역·사회'],
    memberProfiles: [
      { id: 'minjae', name: '정민재', role: '팀장' },
      { id: 'doyun', name: '박도윤', role: '디자이너' },
    ],
  },
];

// [출처 1, 5] 공개된 함께할 사람 예시 데이터
export const mockPeople: Person[] = [
  {
    id: 'seoyeon',
    name: '이서연',
    avatarId: 'arti',
    roles: ['UI/UX 디자이너', '서비스 기획'],
    interests: ['환경', '디자인'],
    intro:
      '사용자 관점에서 문제를 정의하고 직관적인 인터페이스를 만드는 것을 즐깁니다.',
    experience:
      '교내 해커톤 UI/UX 디자인 우수상 수상, 피그마 기반 디자인 시스템 구축 경험',
    academicStatus: '재학',
    grade: '3학년',
    college: '디자인&영상대학',
    department: '디자인학부',
    major: '시각정보디자인전공',
    skills: ['Figma', 'UI/UX', '프로토타이핑'],
    availability: '10~20시간 미만',
    visibility: { discoverable: true },
  },
  {
    id: 'doyun',
    name: '박도윤',
    avatarId: 'dmo',
    roles: ['프론트엔드 개발자'],
    interests: ['IT·기술', '교육'],
    intro:
      'React와 TypeScript로 빠르고 접근성 높은 웹 애플리케이션을 개발합니다.',
    experience:
      '동아리 웹사이트 프론트엔드 리드, 교내 편의 서비스 개발 및 배포 운영',
    academicStatus: '재학',
    grade: '4학년 이상',
    college: '이공대학',
    department: '소프트웨어학과',
    major: '',
    skills: ['React', 'TypeScript', 'Tailwind CSS'],
    availability: '20시간 이상',
    visibility: { discoverable: true },
  },
  {
    id: 'sua',
    name: '최수아',
    avatarId: 'bart',
    roles: ['서비스 기획', '마케팅'],
    interests: ['교육', '기획'],
    intro: '비즈니스 목표와 사용자 니즈의 균형을 맞추는 기획을 지향합니다.',
    experience:
      '스타트업 콘텐츠 마케팅 인턴 3개월, 데이터 기반 온보딩 퍼널 개선',
    academicStatus: '휴학',
    grade: '3학년',
    college: '인문사회과학대학',
    department: '경영학부',
    major: '경영학전공',
    skills: ['서비스 기획', '데이터분석', '문서 작성'],
    availability: '5~10시간 미만',
    visibility: { discoverable: true },
  },
  {
    id: 'minjae',
    name: '정민재',
    avatarId: 'conver',
    roles: ['백엔드 개발자'],
    interests: ['IT·기술', '지역·사회'],
    intro:
      '안정적인 API 설계와 데이터 모델링에 관심이 많은 백엔드 개발자입니다.',
    experience:
      'Spring Boot 및 FastAPI 기반 REST API 개발, 교내 동아리 협업 툴 백엔드 담당',
    academicStatus: '재학',
    grade: '2학년',
    college: '이공대학',
    department: '전자컴퓨터공학과',
    major: '',
    skills: ['Python', 'FastAPI', 'PostgreSQL'],
    availability: '10~20시간 미만',
    visibility: { discoverable: true },
  },
];

// [출처 1, 5] 로그인 본인 프로필 초기값
export const initialMyProfile: Person = {
  id: 'me',
  name: '김서경',
  avatarId: 'skon',
  roles: ['서비스 기획', '프론트엔드 개발자'],
  interests: ['교육', '환경', 'IT·기술'],
  intro: '팀원들과 활발히 소통하며 끝까지 완주하는 프로젝트를 만들고 싶습니다.',
  experience: '웹 개발 동아리 활동, 공모전 1회 참여 경험',
  academicStatus: '재학',
  grade: '3학년',
  college: '이공대학',
  department: '소프트웨어학과',
  major: '',
  skills: ['React', '서비스 기획', 'UI/UX'],
  availability: '10~20시간 미만',
  portfolio: 'https://github.com/wejo-team',
  portfolioTitle: '깃허브 저장소',
  visibility: { discoverable: true },
};

// [출처 1, 5] 내 지원 초기 목록
export const initialApplications: Application[] = [
  {
    id: 'app-1',
    teamId: 'team-campus1',
    role: '개발',
    status: '지원완료',
    message:
      'React와 TypeScript 프로젝트 경험이 있습니다. 캠퍼스 지도 서비스에 꼭 기여하고 싶습니다!',
    submittedAt: '2026.10.19',
  },
  {
    id: 'app-2',
    teamId: 'team-local1',
    role: '기획',
    status: '폐기',
    message: '성북구 지역 상권 활성화에 관심이 많아 지원합니다.',
    submittedAt: '2026.10.16',
    discardReason: '다른 팀 선발로 대기 지원이 폐기됐어요',
  },
];

// [출처 1, 5] 서경대학교 학사 구조 카탈로그
export const academicCatalog = [
  {
    college: '인문사회과학대학',
    department: '글로벌비즈니스어학부',
    majors: ['영어전공', '일어전공', '중어전공', '노어전공', '불어전공'],
  },
  {
    college: '인문사회과학대학',
    department: '공공인재학부',
    majors: ['공공인재전공', '경찰행정전공'],
  },
  {
    college: '인문사회과학대학',
    department: '경영학부',
    majors: ['경영학전공', '글로벌경영학전공'],
  },
  {
    college: '이공대학',
    department: '소프트웨어학과',
    majors: [],
  },
  {
    college: '이공대학',
    department: '전자컴퓨터공학과',
    majors: [],
  },
  {
    college: '디자인&영상대학',
    department: '디자인학부',
    majors: [
      '비주얼디자인전공',
      '시각정보디자인전공',
      '라이프스타일디자인전공',
    ],
  },
  {
    college: '미래융합대학',
    department: '자유전공학부',
    majors: ['전공 미배정', '컴퓨터소프트웨어전공', 'AI빅데이터전공'],
  },
];

export const weeklyAvailabilityOptions = [
  '5시간 미만',
  '5~10시간 미만',
  '10~20시간 미만',
  '20시간 이상',
];

export const roleOptions = [
  '서비스 기획',
  'UI/UX 디자이너',
  '프론트엔드 개발자',
  '백엔드 개발자',
  '데이터분석',
  '마케팅',
  '영상 편집',
];

export const interestOptions = [
  '교육',
  '환경',
  'IT·기술',
  '디자인',
  '지역·사회',
  '기획',
  '문화·예술',
];
