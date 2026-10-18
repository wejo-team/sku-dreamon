import type { Profile } from './data';

// Interaction fixtures copied from docs/specs/academic-structure.md. The verified
// operating-year catalog and permanent codes remain TBD; these are not API enums.
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

export const academicStatuses = ['재학', '휴학', '졸업', '기타'];
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
  '기타',
];

export function missingProfileFields(
  profile: Pick<Profile, 'name' | 'roles' | 'interests'>,
) {
  return [
    !profile.name.trim() && '이름',
    !profile.roles.length && '희망 역할',
    !profile.interests.length && '관심 분야',
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
