/**
 * [참조 출처]
 * 1. docs/api/conventions.md#types - UUID Id, UTC Z 시각, BIGINT 십진 문자열, null/[] 표현
 * 2. docs/api/catalogs.md#catalogs, #academic-unit - Catalogs 일곱 목록, AcademicUnit 트리
 * 3. docs/api/contests.md#contest - Contest·ParticipationCapacity·ContestTiming·DeadlineInterpretation
 * 4. docs/api/profiles.md#profile - Profile 13개 편집 필드와 서버 필드
 * 5. docs/api/teams.md#team-summary, #team-member - TeamSummary·Team·TeamMember 계산값
 * 6. docs/api/applications.md#application - Application 필드
 * 7. docs/api/notifications.md#notification-fields - Notification 필드
 * 8. docs/api/auth.md#account - Account
 * 9. docs/specs/profile-options.md#open-questions - 실제 코드 문자열은 OPTIONS-02·07에서 미정
 * 10. design-reference/src/features/design-preview/data.ts - 변환 전 예시 데이터 원본
 *
 * 화면 확인용 목업이며 서버 계약을 대신하지 않습니다(docs/design/handoff.md 「제품 구현에 옮기는 순서」 3단계).
 * 모든 레코드는 API가 돌려줄 DTO 모양 그대로입니다. 서버가 계산하는 값(registrationStatus, teamCount,
 * memberCount, isRecruiting, isDemo)도 아래 derive 함수로 같은 규칙에 따라 만듭니다.
 */

import type { AcademicUnit, Catalogs } from '@/features/catalogs/api';
import type { Account } from '@/features/auth/api';
import type {
  Contest,
  ContestSummary,
  DeadlineInterpretation,
  RegistrationStatus,
} from '@/features/contests/api';
import type { Profile } from '@/features/profiles/api';
import type {
  MembershipRole,
  Team,
  TeamMember,
  TeamSummary,
} from '@/features/teams/api';
import type {
  Application,
  ApplicationStatus,
} from '@/features/applications/api';
import type { Notification } from '@/features/notifications/api';
import { academicCatalog } from '@/features/demo/profile-fields';

// [출처 1] 재현용 고정 현재 시각(2026-10-18 KST). 운영 시계가 아닙니다.
export const mockNow = Date.parse('2026-10-18T09:00:00Z');

const uuid = (prefix: string, n: number) =>
  `${prefix}-0000-4000-8000-${n.toString(16).padStart(12, '0')}`;

// [출처 1] 읽기 쉬운 이름 → UUID. 화면·테스트는 이 상수로 경로를 만듭니다.
export const demoIds = {
  accounts: {
    me: uuid('aaaaaaaa', 1),
    minjun: uuid('aaaaaaaa', 2),
    doyun: uuid('aaaaaaaa', 3),
    haneul: uuid('aaaaaaaa', 4),
    jiho: uuid('aaaaaaaa', 5),
    yuna: uuid('aaaaaaaa', 6),
    seoyeon: uuid('aaaaaaaa', 7),
    sua: uuid('aaaaaaaa', 8),
    // scenario=team-lifecycle 전용
    seojun: uuid('aaaaaaaa', 9),
    suhyun: uuid('aaaaaaaa', 10),
  },
  contests: {
    campus: uuid('cccccccc', 1),
    green: uuid('cccccccc', 2),
    local: uuid('cccccccc', 3),
    solo: uuid('cccccccc', 4),
    openLab: uuid('cccccccc', 5),
    upcoming: uuid('cccccccc', 6),
    archive: uuid('cccccccc', 7),
  },
  teams: {
    makers: uuid('eeeeeeee', 1),
    greenwave: uuid('eeeeeeee', 2),
    localcrew: uuid('eeeeeeee', 3),
    greenmakers: uuid('eeeeeeee', 4),
    localstudio: uuid('eeeeeeee', 5),
  },
  applications: {
    localcrew: uuid('dddddddd', 1),
    seoyeon: uuid('dddddddd', 2),
    sua: uuid('dddddddd', 3),
    discardedLocal: uuid('dddddddd', 4),
    greenmakersSeoyeon: uuid('dddddddd', 5),
  },
  memberships: {
    makersLeader: uuid('bbbbbbbb', 1),
    makersDoyun: uuid('bbbbbbbb', 2),
    greenwaveLeader: uuid('bbbbbbbb', 3),
    greenwaveHaneul: uuid('bbbbbbbb', 4),
    localcrewLeader: uuid('bbbbbbbb', 5),
    localcrewMe: uuid('bbbbbbbb', 6),
    localcrewYuna: uuid('bbbbbbbb', 7),
    greenmakersLeader: uuid('bbbbbbbb', 8),
    greenmakersSeoyeon: uuid('bbbbbbbb', 9),
    localstudioLeader: uuid('bbbbbbbb', 10),
  },
  notifications: {
    localcrewSelected: uuid('ffffffff', 1),
    seoyeonApplied: uuid('ffffffff', 2),
    suaApplied: uuid('ffffffff', 3),
  },
} as const;

// [출처 8] 서버가 고정 UUID 시드 목록으로 isDemo를 판정합니다. 목업에서 새로 만든 리소스는 false입니다.
const seedIds = new Set<string>(
  Object.values(demoIds).flatMap((group) => Object.values(group)),
);
export const isDemoId = (id: string) => seedIds.has(id);

// 상대 자산 경로 → HttpUrl. 계약상 posterUrl·assetUrl·sourceUrl은 절대 URL입니다.
const origin = () => globalThis.location?.origin ?? 'http://localhost:5173';
export const absoluteUrl = (path: string) => new URL(path, origin()).href;

// [출처 2, 9] 목업 전용 임시 코드. 표시명은 기존 화면 문구 그대로입니다.
const items = (pairs: [string, string][]) =>
  pairs.map(([code, displayName], index) => ({
    code,
    displayName,
    isSelectable: true,
    sortOrder: index + 1,
  }));

export const fixtureCatalogs = (): Catalogs => ({
  fields: items([
    ['it_tech', 'IT·기술'],
    ['business', '경영·창업'],
    ['design', '디자인'],
    ['society_culture', '사회·문화'],
    ['environment', '환경'],
    ['education', '교육'],
    ['media_content', '미디어·콘텐츠'],
    ['health_medical', '보건·의료'],
    ['policy', '정책'],
    ['public', '공공'],
  ]),
  roles: items([
    ['planning', '기획'],
    ['design', '디자인'],
    ['development', '개발'],
    ['research', '자료조사'],
    ['presentation', '발표'],
    ['marketing', '마케팅'],
  ]),
  skills: items([
    ['programming', '프로그래밍'],
    ['ui_ux', 'UI/UX'],
    ['data_analysis', '데이터분석'],
    ['video_editing', '영상 편집'],
    ['document_writing', '문서 작성'],
    ['service_planning', '서비스 기획'],
    ['market_research', '시장 조사'],
    ['graphic_design', '그래픽 디자인'],
    ['slide_making', 'PPT 제작'],
    ['data_visualization', '데이터 시각화'],
    ['sns_marketing', 'SNS 마케팅'],
    ['content_planning', '콘텐츠 기획'],
    ['public_speaking', '발표·스피치'],
  ]),
  academicStatuses: items([
    ['enrolled', '재학'],
    ['on_leave', '휴학'],
    ['graduated', '졸업'],
  ]),
  grades: items([
    ['grade_1', '1학년'],
    ['grade_2', '2학년'],
    ['grade_3', '3학년'],
    ['grade_4_plus', '4학년 이상'],
    ['not_applicable', '해당 없음'],
  ]),
  weeklyAvailabilityRanges: items([
    ['under_5', '5시간 미만'],
    ['from_5_to_10', '5~10시간 미만'],
    ['from_10_to_20', '10~20시간 미만'],
    ['over_20', '20시간 이상'],
  ]),
  avatarPresets: items([
    ['skon', '스콘'],
    ['arti', '아티'],
    ['dmo', '디모'],
    ['bart', '비아트'],
    ['conver', '컨버'],
  ]).map((item) => ({
    ...item,
    assetUrl: absoluteUrl(`/mascots/${item.code}.png`),
  })),
});

// [출처 2] 학사 트리: 단과대학(parentId=null) → 학부·학과 → 전공. ID는 증가형 십진 문자열
export function fixtureAcademicUnits(): AcademicUnit[] {
  const units: AcademicUnit[] = [];
  const colleges = new Map<string, string>();
  let next = 1;
  const add = (name: string, parentId: string | null) => {
    const id = String(next++);
    units.push({ id, name, parentId, isSelectable: true });
    return id;
  };
  for (const entry of academicCatalog) {
    let collegeId = colleges.get(entry.college);
    if (!collegeId) {
      collegeId = add(entry.college, null);
      colleges.set(entry.college, collegeId);
    }
    const departmentId = add(entry.department, collegeId);
    for (const major of 'majors' in entry ? entry.majors : [])
      add(major, departmentId);
  }
  return units;
}

// [출처 3] 원문에 시각·시간대가 없으면 한국시간 날짜 끝(다음 날 00:00, 제외 경계)으로 보완
const kstDateEnd = (date: string): DeadlineInterpretation => ({
  sourceDate: date,
  sourceTime: null,
  sourceTimeZone: null,
  effectiveTimeZone: 'Asia/Seoul',
  timeDefaulted: true,
  timeZoneDefaulted: true,
});

type ContestSeed = Omit<
  Contest,
  'registrationStatus' | 'teamCount' | 'isDemo' | 'version'
>;

const contestSeed = ({
  key,
  title,
  fieldCodes,
  poster,
  opens,
  startsAt,
  closing,
  endsAt,
  createdAt,
  audienceCodes,
  eligibilityText,
  capacity,
  description,
  deliverables,
}: {
  key: keyof typeof demoIds.contests;
  title: string;
  fieldCodes: string[];
  poster: string | null;
  opens: string;
  startsAt: string;
  closing: DeadlineInterpretation;
  endsAt: string;
  createdAt: string;
  audienceCodes: Contest['audienceCodes'];
  eligibilityText: string;
  capacity: Contest['capacity'];
  description: string;
  deliverables: string;
}): ContestSeed => ({
  id: demoIds.contests[key],
  title,
  organizer: '드림온 운영팀',
  fieldCodes,
  posterUrl: poster ? absoluteUrl(poster) : null,
  startsAt,
  endsAt,
  createdAt,
  description,
  audienceCodes,
  eligibilityText,
  capacity,
  timing: {
    startsAt,
    endsAt,
    openSourceDate: opens,
    openSourceTime: null,
    openSourceTimeZone: null,
    openEffectiveTimeZone: 'Asia/Seoul',
    openTimeZoneDefaulted: true,
    closing,
  },
  deliverables,
  awards: null,
  contact: null,
  verifiedAt: '2026-10-17T15:00:00Z',
  sourceUrl: absoluteUrl(
    `/reference/notices/${key === 'openLab' ? 'open-lab' : key}`,
  ),
});

const range = (min: number, max: number): Contest['capacity'] => ({
  kind: 'range',
  minimumMembers: String(min),
  maximumMembers: String(max),
});

// [출처 3, 10] 공모전 원본. 등록순(createdAt DESC)이 기존 화면의 순서와 같도록 생성 시각을 둡니다.
const contestSeeds: ContestSeed[] = [
  contestSeed({
    key: 'campus',
    title: '더 나은 캠퍼스 아이디어 공모전',
    fieldCodes: ['education', 'it_tech'],
    poster: '/contest-covers/campus.webp',
    opens: '2026-10-01',
    startsAt: '2026-09-30T15:00:00Z',
    closing: kstDateEnd('2026-11-08'),
    endsAt: '2026-11-08T15:00:00Z',
    createdAt: '2026-10-17T06:00:00Z',
    audienceCodes: ['student'],
    eligibilityText: '대학생 누구나',
    capacity: range(2, 5),
    description:
      '우리가 매일 지나는 캠퍼스를 더 편리하게 만드는 아이디어를 제안해요. 문제 발견부터 해결 방향까지, 다양한 전공의 관점을 모아보세요.',
    deliverables: '아이디어 제안서 PDF · 발표 자료',
  }),
  contestSeed({
    key: 'green',
    title: '일상 속 그린테크 챌린지',
    fieldCodes: ['environment', 'it_tech'],
    poster: '/contest-covers/green.webp',
    opens: '2026-10-01',
    startsAt: '2026-09-30T15:00:00Z',
    closing: kstDateEnd('2026-10-25'),
    endsAt: '2026-10-25T15:00:00Z',
    createdAt: '2026-10-17T05:00:00Z',
    audienceCodes: ['student'],
    eligibilityText: '대학생·대학원생',
    capacity: range(2, 4),
    description:
      '일상에서 시작할 수 있는 환경 문제를 찾고, 기술로 해결 방법을 제안해요. 작지만 실현할 수 있는 변화를 함께 만들어보세요.',
    deliverables: '기획서 · 프로토타입 소개 영상',
  }),
  contestSeed({
    key: 'local',
    title: '우리 동네를 새롭게, 로컬 브랜딩',
    fieldCodes: ['design', 'society_culture'],
    poster: null,
    opens: '2026-10-01',
    startsAt: '2026-09-30T15:00:00Z',
    closing: kstDateEnd('2026-11-15'),
    endsAt: '2026-11-15T15:00:00Z',
    createdAt: '2026-10-17T04:00:00Z',
    audienceCodes: ['student'],
    eligibilityText: '대학생 누구나',
    capacity: range(2, 3),
    description:
      '지역의 고유한 이야기를 발견하고 새로운 시각으로 표현해요. 브랜드 기획과 시각 디자인을 연결하는 팀을 기다립니다.',
    deliverables: '브랜드 제안서 · 시각 디자인 시안',
  }),
  contestSeed({
    key: 'solo',
    title: '한 장으로 전하는 캠퍼스 이야기',
    fieldCodes: ['design', 'media_content'],
    poster: null,
    opens: '2026-10-01',
    startsAt: '2026-09-30T15:00:00Z',
    // 원문에 시각·시간대가 있어 보완하지 않음
    closing: {
      sourceDate: '2026-11-20',
      sourceTime: '18:00',
      sourceTimeZone: 'Asia/Seoul',
      effectiveTimeZone: 'Asia/Seoul',
      timeDefaulted: false,
      timeZoneDefaulted: false,
    },
    endsAt: '2026-11-20T09:00:00Z',
    createdAt: '2026-10-17T03:00:00Z',
    audienceCodes: ['student'],
    eligibilityText: '대학생 개인 참가',
    capacity: range(1, 1),
    description: '나만의 시선으로 캠퍼스 이야기를 한 장의 포스터에 담아보세요.',
    deliverables: '포스터 이미지',
  }),
  contestSeed({
    key: 'openLab',
    title: '함께 만드는 열린 아이디어 실험실',
    fieldCodes: ['it_tech', 'society_culture'],
    poster: null,
    opens: '2026-10-01',
    startsAt: '2026-09-30T15:00:00Z',
    closing: kstDateEnd('2026-11-25'),
    endsAt: '2026-11-25T15:00:00Z',
    createdAt: '2026-10-17T02:00:00Z',
    audienceCodes: ['student', 'general'],
    eligibilityText: '대학생 및 일반인, 팀 인원 상한 없음',
    capacity: { kind: 'unlimited', minimumMembers: '1', maximumMembers: null },
    description:
      '여러 사람의 관점을 모아 일상 속 아이디어를 작은 실험으로 만들어보세요.',
    deliverables: '프로젝트 소개서',
  }),
  contestSeed({
    key: 'upcoming',
    title: '다음 캠퍼스를 상상하는 공모전',
    fieldCodes: ['education', 'environment'],
    poster: null,
    opens: '2026-11-01',
    startsAt: '2026-10-31T15:00:00Z',
    closing: kstDateEnd('2026-12-01'),
    endsAt: '2026-12-01T15:00:00Z',
    createdAt: '2026-10-17T01:00:00Z',
    audienceCodes: ['unrestricted'],
    eligibilityText: '참가 대상 제한 없음',
    capacity: range(2, 4),
    description:
      '더 나은 캠퍼스를 위한 새로운 제안을 기다립니다. 접수 시작 전 공고를 먼저 확인해 보세요.',
    deliverables: '제안서',
  }),
  contestSeed({
    key: 'archive',
    title: '지난 캠퍼스 아이디어 공모전',
    fieldCodes: ['education', 'it_tech'],
    poster: '/contest-covers/campus.webp',
    opens: '2026-08-01',
    startsAt: '2026-07-31T15:00:00Z',
    closing: kstDateEnd('2026-09-30'),
    endsAt: '2026-09-30T15:00:00Z',
    createdAt: '2026-08-01T00:00:00Z',
    audienceCodes: ['student'],
    eligibilityText: '대학생 누구나',
    capacity: range(2, 5),
    description:
      '우리가 매일 지나는 캠퍼스를 더 편리하게 만드는 아이디어를 제안해요. 문제 발견부터 해결 방향까지, 다양한 전공의 관점을 모아보세요.',
    deliverables: '아이디어 제안서 PDF · 발표 자료',
  }),
];

// [출처 4] 프로필. 미선택 이미지는 null(화면 기본 스콘)
type ProfileSeed = Pick<Profile, 'accountId' | 'realName'> &
  Partial<Omit<Profile, 'accountId' | 'realName'>>;
const profile = (seed: ProfileSeed): Profile => ({
  version: '1',
  isPublic: false,
  isDemo: true,
  updatedAt: '2026-10-10T00:00:00Z',
  profileImageCode: null,
  academicStatusCode: null,
  gradeCode: null,
  weeklyAvailabilityCode: null,
  academicUnitId: null,
  experienceState: 'unspecified',
  experienceBody: null,
  introduction: null,
  fieldCodes: [],
  roleCodes: [],
  skillCodes: [],
  portfolio: null,
  ...seed,
});

const a = demoIds.accounts;
export const fixtureProfiles = (): Profile[] => [
  profile({
    accountId: a.me,
    realName: '김지우',
    introduction:
      '다양한 전공의 사람들과 의미 있는 프로젝트를 완성하고 싶어요.',
    fieldCodes: ['it_tech', 'education'],
    roleCodes: ['planning'],
  }),
  profile({
    accountId: a.seoyeon,
    realName: '김서연',
    isPublic: true,
    updatedAt: '2026-10-16T00:00:00Z',
    profileImageCode: 'arti',
    fieldCodes: ['it_tech', 'environment'],
    roleCodes: ['development'],
    skillCodes: ['programming', 'ui_ux'],
    experienceState: 'provided',
    experienceBody: '교내 서비스 프로젝트에서 화면 개발을 담당했어요.',
    introduction: '함께 배우며 완성하는 팀을 찾고 있어요.',
    portfolio: {
      url: absoluteUrl('/reference/portfolios/seoyeon'),
      title: '김서연의 프로젝트',
    },
  }),
  profile({
    accountId: a.doyun,
    realName: '이도윤',
    isPublic: true,
    updatedAt: '2026-10-15T00:00:00Z',
    profileImageCode: 'dmo',
    fieldCodes: ['it_tech', 'design'],
    roleCodes: ['development'],
    introduction:
      '아이디어를 동작하는 화면으로 만드는 프론트엔드 개발에 관심이 있어요.',
  }),
  profile({
    accountId: a.sua,
    realName: '정수아',
    isPublic: true,
    updatedAt: '2026-10-14T00:00:00Z',
    profileImageCode: 'bart',
    fieldCodes: ['design', 'environment'],
    roleCodes: ['design'],
    skillCodes: ['ui_ux', 'graphic_design'],
    experienceState: 'provided',
    experienceBody: '브랜딩 프로젝트 경험',
    introduction: '사용자 관점에서 설계합니다.',
  }),
  profile({
    accountId: a.minjun,
    realName: '박민준',
    fieldCodes: ['education'],
    roleCodes: ['planning'],
  }),
  profile({
    accountId: a.haneul,
    realName: '최하늘',
    fieldCodes: ['environment'],
    roleCodes: ['research'],
  }),
  profile({
    accountId: a.jiho,
    realName: '서지호',
    fieldCodes: ['design'],
    roleCodes: ['design'],
  }),
  profile({
    accountId: a.yuna,
    realName: '한유나',
    fieldCodes: ['society_culture'],
    roleCodes: ['presentation'],
  }),
];

// [출처 8] 데모 계정 = 김지우. loginId는 docs/design/handoff.md의 공개 확인용 값
export const fixtureAccount = (): Account => ({
  id: a.me,
  loginId: 'dreamondemo',
  isDemo: true,
  hasProfile: true,
  schoolVerification: 'unverified',
  createdAt: '2026-10-01T00:00:00Z',
});

// [출처 5] 팀 원본(계산값 제외)과 현재 소속
export type TeamRecord = Omit<
  Team,
  | 'contestTitle'
  | 'fieldCodes'
  | 'memberCount'
  | 'isRecruiting'
  | 'isDemo'
  | 'contest'
>;
export type MembershipRecord = {
  membershipId: string;
  teamId: string;
  accountId: string;
  membershipRole: MembershipRole;
  roleCode: string | null;
  joinedAt: string;
  /** 선발 후 취소 등으로 끝난 소속. 현재 소속은 null */
  endedAt: string | null;
};

const t = demoIds.teams;
const m = demoIds.memberships;
export const fixtureTeams = (): TeamRecord[] => [
  {
    id: t.makers,
    version: '1',
    contestId: demoIds.contests.campus,
    name: '캠퍼스 메이커스',
    introduction:
      '캠퍼스 생활의 작은 불편을 함께 해결할 기획자와 디자이너를 찾고 있어요.',
    roleCodes: ['planning', 'design'],
    capacity: '4',
    recruitmentState: 'open',
    closedReason: null,
    recruitmentEndsAt: '2026-11-05T15:00:00Z',
    createdAt: '2026-10-08T00:00:00Z',
    recruitmentDeadline: kstDateEnd('2026-11-05'),
    ownerAccountId: a.minjun,
  },
  {
    id: t.greenwave,
    version: '1',
    contestId: demoIds.contests.green,
    name: '그린웨이브',
    introduction:
      '환경과 기술 사이, 실행할 수 있는 아이디어를 만드는 팀이에요.',
    roleCodes: ['development', 'design'],
    capacity: '4',
    recruitmentState: 'open',
    closedReason: null,
    recruitmentEndsAt: '2026-10-24T15:00:00Z',
    createdAt: '2026-10-07T00:00:00Z',
    recruitmentDeadline: kstDateEnd('2026-10-24'),
    ownerAccountId: a.me,
  },
  {
    id: t.localcrew,
    version: '2',
    contestId: demoIds.contests.local,
    name: '로컬 크루',
    introduction: '동네의 이야기를 브랜드로 만드는 프로젝트를 준비하고 있어요.',
    roleCodes: ['planning'],
    capacity: '3',
    recruitmentState: 'closed',
    closedReason: 'capacity_reached',
    recruitmentEndsAt: '2026-11-10T15:00:00Z',
    createdAt: '2026-10-06T00:00:00Z',
    recruitmentDeadline: kstDateEnd('2026-11-10'),
    ownerAccountId: a.jiho,
  },
];

export const fixtureMemberships = (): MembershipRecord[] => [
  {
    membershipId: m.makersLeader,
    teamId: t.makers,
    accountId: a.minjun,
    membershipRole: 'leader',
    roleCode: null,
    joinedAt: '2026-10-08T00:00:00Z',
    endedAt: null,
  },
  {
    membershipId: m.makersDoyun,
    teamId: t.makers,
    accountId: a.doyun,
    membershipRole: 'member',
    roleCode: 'development',
    joinedAt: '2026-10-09T00:00:00Z',
    endedAt: null,
  },
  {
    membershipId: m.greenwaveLeader,
    teamId: t.greenwave,
    accountId: a.me,
    membershipRole: 'leader',
    roleCode: null,
    joinedAt: '2026-10-07T00:00:00Z',
    endedAt: null,
  },
  {
    membershipId: m.greenwaveHaneul,
    teamId: t.greenwave,
    accountId: a.haneul,
    membershipRole: 'member',
    roleCode: 'research',
    joinedAt: '2026-10-09T00:00:00Z',
    endedAt: null,
  },
  {
    membershipId: m.localcrewLeader,
    teamId: t.localcrew,
    accountId: a.jiho,
    membershipRole: 'leader',
    roleCode: null,
    joinedAt: '2026-10-06T00:00:00Z',
    endedAt: null,
  },
  {
    membershipId: m.localcrewMe,
    teamId: t.localcrew,
    accountId: a.me,
    membershipRole: 'member',
    roleCode: 'planning',
    joinedAt: '2026-10-11T00:00:00Z',
    endedAt: null,
  },
  {
    membershipId: m.localcrewYuna,
    teamId: t.localcrew,
    accountId: a.yuna,
    membershipRole: 'member',
    roleCode: 'presentation',
    joinedAt: '2026-10-12T00:00:00Z',
    endedAt: null,
  },
];

// [출처 6] 지원 원본
const application = (
  seed: Pick<
    Application,
    | 'id'
    | 'teamId'
    | 'contestId'
    | 'applicantAccountId'
    | 'roleCode'
    | 'message'
    | 'status'
  > &
    Partial<Application>,
): Application => ({
  version: '1',
  discardReason: null,
  discardedByApplicationId: null,
  discardedByTeamId: null,
  submittedAt: '2026-10-10T00:00:00Z',
  updatedAt: '2026-10-10T00:00:00Z',
  ...seed,
});

export const fixtureApplications = (): Application[] => [
  application({
    id: demoIds.applications.localcrew,
    version: '2',
    teamId: t.localcrew,
    contestId: demoIds.contests.local,
    applicantAccountId: a.me,
    roleCode: 'planning',
    message: '브랜드 기획을 함께하고 싶어요.',
    status: 'selected',
    submittedAt: '2026-10-09T00:00:00Z',
    updatedAt: '2026-10-11T00:00:00Z',
  }),
  application({
    id: demoIds.applications.seoyeon,
    version: '2',
    teamId: t.greenwave,
    contestId: demoIds.contests.green,
    applicantAccountId: a.seoyeon,
    roleCode: 'development',
    message:
      '환경 문제를 해결하는 서비스에 관심이 있어요. 프론트엔드 개발을 맡고, 기획도 함께 고민하고 싶습니다.',
    status: 'reviewing',
    submittedAt: '2026-10-15T00:00:00Z',
    updatedAt: '2026-10-16T00:00:00Z',
  }),
  application({
    id: demoIds.applications.sua,
    version: '2',
    teamId: t.greenwave,
    contestId: demoIds.contests.green,
    applicantAccountId: a.sua,
    roleCode: 'design',
    message:
      '사용자 리서치부터 화면 설계까지 함께하고 싶어요. 환경을 위한 작은 행동을 쉽게 만드는 경험에 관심이 있습니다.',
    status: 'reviewing',
    submittedAt: '2026-10-14T00:00:00Z',
    updatedAt: '2026-10-16T00:00:00Z',
  }),
];

// [출처 7] 사건 발생 당시 상태로 만든 제목·본문
export const applicationStatusTitles: Record<ApplicationStatus, string> = {
  canceled: '지원이 취소됐어요',
  submitted: '지원이 접수됐어요',
  reviewing: '팀에서 지원서를 검토하고 있어요',
  selected: '지원한 팀에서 선발됐어요',
  rejected: '이번 모집에서는 선발되지 않았어요',
  discarded: '다른 팀 선발로 대기 지원이 폐기됐어요',
};

// 각 알림의 수신자. Notification DTO에는 없는 서버 내부 정보입니다.
// 수신자와 발생 건 키(중복 방지)는 서버 내부 정보로, Notification 응답에는 없습니다.
export type NotificationRecord = Notification & {
  recipientAccountId: string;
  eventKey: string;
};

// 수신자는 서버 내부 정보이므로 Notification 응답에서 뺍니다.
export function toNotificationDto(record: NotificationRecord): Notification {
  const notification: Partial<NotificationRecord> = { ...record };
  delete notification.recipientAccountId;
  delete notification.eventKey;
  return notification as Notification;
}

export const fixtureNotifications = (): NotificationRecord[] => [
  {
    id: demoIds.notifications.localcrewSelected,
    eventKey: `history:${demoIds.applications.localcrew}:applicant`,
    recipientAccountId: a.me,
    kind: 'application_status_changed',
    applicationId: demoIds.applications.localcrew,
    teamId: t.localcrew,
    eventStatus: 'selected',
    occurredAt: '2026-10-11T00:00:00Z',
    readAt: null,
    title: applicationStatusTitles.selected,
    body: '로컬 크루 · 기획 지원',
  },
  {
    id: demoIds.notifications.seoyeonApplied,
    eventKey: `history:${demoIds.applications.seoyeon}:leader`,
    recipientAccountId: a.me,
    kind: 'new_application',
    applicationId: demoIds.applications.seoyeon,
    teamId: t.greenwave,
    eventStatus: 'submitted',
    occurredAt: '2026-10-15T00:00:00Z',
    readAt: null,
    title: '김서연 님이 지원했어요',
    body: '그린웨이브 · 개발 지원',
  },
  {
    id: demoIds.notifications.suaApplied,
    eventKey: `history:${demoIds.applications.sua}:leader`,
    recipientAccountId: a.me,
    kind: 'new_application',
    applicationId: demoIds.applications.sua,
    teamId: t.greenwave,
    eventStatus: 'submitted',
    occurredAt: '2026-10-14T00:00:00Z',
    readAt: null,
    title: '정수아 님이 지원했어요',
    body: '그린웨이브 · 디자인 지원',
  },
];

// ─── 서버 계산값 ──────────────────────────────────────────────

// [출처 3] 접수 예정·중·마감. startsAt 포함, endsAt 제외 경계
export function registrationStatusAt(
  contest: Pick<Contest, 'startsAt' | 'endsAt'>,
  now = mockNow,
): RegistrationStatus {
  if (now >= Date.parse(contest.endsAt)) return 'closed';
  return now < Date.parse(contest.startsAt) ? 'scheduled' : 'open';
}

export type DemoRecords = {
  contests: ContestSeed[];
  teams: TeamRecord[];
  memberships: MembershipRecord[];
};

// [출처 3] 공고 상세. teamCount는 상태와 관계없는 연결 팀 전체 수
export function deriveContest(
  seed: ContestSeed,
  records: Pick<DemoRecords, 'teams'>,
  now = mockNow,
): Contest {
  return {
    ...seed,
    registrationStatus: registrationStatusAt(seed, now),
    teamCount: records.teams.filter((team) => team.contestId === seed.id)
      .length,
    isDemo: isDemoId(seed.id),
    version: '1',
  };
}

export function toContestSummary(contest: Contest): ContestSummary {
  return {
    id: contest.id,
    title: contest.title,
    organizer: contest.organizer,
    fieldCodes: contest.fieldCodes,
    posterUrl: contest.posterUrl,
    registrationStatus: contest.registrationStatus,
    startsAt: contest.startsAt,
    endsAt: contest.endsAt,
    teamCount: contest.teamCount,
    isDemo: contest.isDemo,
    createdAt: contest.createdAt,
    version: contest.version,
  };
}

export const currentMemberships = (
  memberships: MembershipRecord[],
  teamId: string,
) => memberships.filter((item) => item.teamId === teamId && !item.endedAt);

// [출처 5] 공통 모집 가능 표시: 저장 상태 open + 공고 접수 중 + 팀 기한 전 + 잔여 정원
export function deriveTeam(
  team: TeamRecord,
  records: DemoRecords,
  now = mockNow,
): Team {
  const seed = records.contests.find((item) => item.id === team.contestId);
  if (!seed) throw new Error(`contest ${team.contestId} not found`);
  const contest = deriveContest(seed, records, now);
  const memberCount = currentMemberships(records.memberships, team.id).length;
  const isRecruiting =
    team.recruitmentState === 'open' &&
    contest.registrationStatus === 'open' &&
    now < Date.parse(team.recruitmentEndsAt) &&
    memberCount < Number(team.capacity);
  return {
    ...team,
    contestTitle: contest.title,
    fieldCodes: contest.fieldCodes,
    memberCount,
    isRecruiting,
    isDemo: isDemoId(team.id),
    contest: toContestSummary(contest),
  };
}

export function toTeamSummary(team: Team): TeamSummary {
  return {
    id: team.id,
    version: team.version,
    contestId: team.contestId,
    contestTitle: team.contestTitle,
    name: team.name,
    introduction: team.introduction,
    fieldCodes: team.fieldCodes,
    roleCodes: team.roleCodes,
    capacity: team.capacity,
    memberCount: team.memberCount,
    recruitmentState: team.recruitmentState,
    closedReason: team.closedReason,
    recruitmentEndsAt: team.recruitmentEndsAt,
    isRecruiting: team.isRecruiting,
    isDemo: team.isDemo,
    createdAt: team.createdAt,
    recruitmentDeadline: team.recruitmentDeadline,
  };
}

// [출처 5] 소속 표시. profile은 본인·공개 프로필·지원받은 팀장 권한에서만
export function toTeamMember(
  membership: MembershipRecord,
  profiles: Profile[],
  canViewProfile: (profile: Profile) => boolean,
): TeamMember {
  const memberProfile = profiles.find(
    (item) => item.accountId === membership.accountId,
  );
  return {
    membershipId: membership.membershipId,
    accountId: membership.accountId,
    realName: memberProfile?.realName ?? '',
    isDemo: isDemoId(membership.accountId),
    membershipRole: membership.membershipRole,
    roleCode: membership.roleCode,
    joinedAt: membership.joinedAt,
    profile:
      memberProfile && canViewProfile(memberProfile) ? memberProfile : null,
  };
}

// 전체 목업 레코드의 새 복사본. 목업 서버와 DemoProvider가 같은 원본을 사용합니다.
export function createDemoRecords() {
  return {
    account: fixtureAccount(),
    catalogs: fixtureCatalogs(),
    academicUnits: fixtureAcademicUnits(),
    contests: structuredClone(contestSeeds),
    profiles: fixtureProfiles(),
    teams: fixtureTeams(),
    memberships: fixtureMemberships(),
    applications: fixtureApplications(),
    notifications: fixtureNotifications(),
  };
}
export type DemoDatabase = ReturnType<typeof createDemoRecords>;
export type { ContestSeed };
