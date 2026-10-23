/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/profile-fields.ts - 프로필 선택지·검증 원본
 * 2. docs/specs/profile-options.md - 학적·학년·역량·주당 시간 4구간, 기타 제거
 * 3. docs/specs/profile.md#input-validation - 이름 50·소개 300·경험 500·제목 50자, 앞뒤 공백 제거 후 검증
 * 4. docs/specs/academic-structure.md - 학사 종속 선택
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import type { Profile } from '@/features/demo/data';

// Interaction fixtures copied from docs/specs/academic-structure.md. The verified
// operating-year catalog and permanent codes remain TBD; these are not API enums.
// [출처 4] 소속별 학사 예시(동명 학과를 동일 학과로 연결하지 않음)
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
    college: '인문사회과학대학',
    department: '광고홍보콘텐츠학과',
    majors: [],
  },
  {
    college: '인문사회과학대학',
    department: '아동청소년학과',
    majors: [],
  },
  {
    college: '인문사회과학대학',
    department: '군사학과',
    majors: [],
  },
  {
    college: '이공대학',
    department: '소프트웨어학과',
    majors: [],
  },
  {
    college: '이공대학',
    department: '금융정보공학과',
    majors: [],
  },
  {
    college: '이공대학',
    department: '전자컴퓨터공학과',
    majors: [],
  },
  {
    college: '이공대학',
    department: '나노화학생명공학과',
    majors: [],
  },
  {
    college: '이공대학',
    department: '물류시스템공학과',
    majors: [],
  },
  {
    college: '이공대학',
    department: '도시공학과',
    majors: [],
  },
  {
    college: '이공대학',
    department: '토목건축공학과',
    majors: [],
  },
  {
    college: '미래융합대학',
    department: '미래융합학부1',
    majors: [
      '글로벌비즈니스전공',
      '인텔리전트비즈니스전공',
      '컴퓨터소프트웨어전공',
      'AI빅데이터전공',
      '파이낸스앤테크전공',
      '비즈니스영어전공',
      '비즈니스일어전공',
      '비즈니스불어전공',
    ],
  },
  {
    college: '미래융합대학',
    department: '미래융합학부2',
    majors: [
      '공공행정전공',
      '경찰행정전공',
      'AI소프트웨어전공',
      'AI시스템전공',
      '아동청소년교육전공',
      '인텔리전트컴퓨팅전공',
      '인텔리전트디바이스전공',
    ],
  },
  {
    college: '미래융합대학',
    department: '자유전공학부',
    majors: [
      '전공 미배정',
      '글로벌비즈니스전공',
      '인텔리전트비즈니스전공',
      '컴퓨터소프트웨어전공',
      'AI빅데이터전공',
      '파이낸스앤테크전공',
      '비즈니스영어전공',
      '비즈니스일어전공',
      '비즈니스불어전공',
      '공공행정전공',
      '경찰행정전공',
      'AI소프트웨어전공',
      'AI시스템전공',
      '아동청소년교육전공',
      '인텔리전트컴퓨팅전공',
      '인텔리전트디바이스전공',
    ],
  },
  {
    college: '미래융합대학',
    department: '군사학과',
    majors: [],
  },
  {
    college: '미래융합대학',
    department: '아트앤테크놀로지학과',
    majors: [],
  },
  {
    college: '미래융합대학',
    department: '스포츠앤테크놀로지학과',
    majors: [],
  },
  {
    college: '디자인&영상대학',
    department: '디자인학부',
    majors: [
      '비주얼디자인전공',
      '라이프스타일디자인전공',
      '시각정보디자인전공',
      '생활문화디자인전공',
    ],
  },
  {
    college: '디자인&영상대학',
    department: '영화영상학과',
    majors: [],
  },
  {
    college: '디자인&영상대학',
    department: '광고홍보영상학과',
    majors: [],
  },
  {
    college: '미용예술대학',
    department: '헤어디자인학과',
    majors: [],
  },
  {
    college: '미용예술대학',
    department: '메이크업디자인학과',
    majors: [],
  },
  {
    college: '미용예술대학',
    department: '코스메틱뷰티매니지먼트학과',
    majors: [],
  },
  {
    college: '미용예술대학',
    department: '글로벌뷰티테라피&코스메틱학과',
    majors: [],
  },
  {
    college: '미용예술대학',
    department: '글로벌메이크업디자인학과',
    majors: [],
  },
  {
    college: '공연예술대학',
    department: '공연예술학부',
    majors: [
      '연기전공',
      '연출전공',
      '무대기술전공',
      '모델연기전공',
      '무대패션전공',
      '뮤지컬전공',
    ],
  },
  {
    college: '공연예술대학',
    department: '음악학부',
    majors: ['피아노전공', '관현악전공'],
  },
  {
    college: '공연예술대학',
    department: '실용음악학부',
    majors: ['기악전공', '작곡전공', '보컬전공', '싱어송라이터전공'],
  },
  {
    college: '공연예술대학',
    department: '무용예술학부',
    majors: ['한국무용전공', '실용무용전공'],
  },
] as const;

export const academicStatuses = ['재학', '휴학', '졸업'];
export const grades = ['1학년', '2학년', '3학년', '4학년 이상', '해당 없음'];
export const skillOptions = [
  '프로그래밍',
  'UI/UX',
  '데이터분석',
  '영상 편집',
  '문서 작성',
  '서비스 기획',
  '시장 조사',
  '그래픽 디자인',
  'PPT 제작',
  '데이터 시각화',
  'SNS 마케팅',
  '콘텐츠 기획',
  '발표·스피치',
];

// [출처 2] 모든 프로젝트 합산 4구간, 미입력과 구분
export const weeklyAvailabilityOptions = [
  '5시간 미만',
  '5~10시간 미만',
  '10~20시간 미만',
  '20시간 이상',
];

// Preview counting convention; the production non-password Unicode contract
// remains TBD. Leading/trailing whitespace is omitted, internal whitespace counts.
// [출처 3] 코드 포인트 기준 길이
// [출처 3] 포트폴리오 주소의 단일 기준: http/https만 허용하고 URL 표준 형태(href)로 정규화합니다.
// 폼 검증·저장·공개 변환이 같은 함수를 써서 저장한 링크와 공개되는 링크가 일치합니다(PR #121 리뷰).
// 예: 'https:/example.com/portfolio' → 'https://example.com/portfolio', 허용하지 않는 값은 ''.
export function normalizeWebUrl(value: string) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

export const profileTextLength = (value: string) =>
  Array.from(value.trim()).length;

// [출처 3] 지원 전 필수 프로필 점검
export function missingProfileFields(
  profile: Pick<Profile, 'name' | 'roles' | 'interests'>,
) {
  return [
    (!profile.name.trim() || profileTextLength(profile.name) > 50) && '이름',
    (!profile.roles.length || profile.roles.length > 2) && '희망 역할',
    (!profile.interests.length || profile.interests.length > 3) && '관심 분야',
  ].filter((field): field is string => !!field);
}

export function academicOptions(college: string, department: string) {
  const departments = academicCatalog.filter(
    (item) => item.college === college,
  );
  return {
    colleges: [...new Set(academicCatalog.map((item) => item.college))],
    departments: departments.map((item) => item.department),
    majors:
      departments.find((item) => item.department === department)?.majors ?? [],
  };
}
