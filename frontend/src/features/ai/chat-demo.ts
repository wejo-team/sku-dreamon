/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/chat-demo.ts - 모의 대화 응답 원본
 * 2. docs/design/handoff.md - 실제 모델 호출 없이 대화·추천 카드 동작 확인
 * 3. docs/specs/matching.md#acceptance-criteria - 본인·소속 팀 제외, 공개 범위·모집 조건 재검사
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import type { Application, Contest, Person, Team } from '@/features/demo/data';
import {
  contestDeadline,
  deadlineLabel,
  isContestOpen,
} from '@/features/demo/contest-state';
import { isTeamMember, recruitmentIssue } from '@/features/demo/team-state';

export type ChatSearchState = {
  kind: 'contests' | 'teams' | 'people';
  role?: string;
  category?: string;
  deadlineFirst?: boolean;
  keyword?: string;
  shownIds?: string[];
};

export type ChatRecommendation = {
  kind: 'contest' | 'team' | 'person';
  id: string;
  reason: string;
};

export type ChatReply = {
  text: string;
  recommendations: ChatRecommendation[];
  suggestions: string[];
  search: ChatSearchState;
};

type SearchData = {
  contests: Contest[];
  teams: Team[];
  people: Person[];
  applications?: Application[];
};

function availableTeam(team: Team, data: SearchData) {
  const contest = data.contests.find((item) => item.id === team.contestId);
  return Boolean(
    contest &&
    isContestOpen(contest) &&
    !recruitmentIssue(team) &&
    !isTeamMember(team) &&
    !data.applications?.some(
      (item) => item.teamId === team.id && item.status !== '지원취소',
    ),
  );
}

const startingQuestions = [
  '마감이 가까운 공모전 찾아줘',
  '개발자를 모집하는 팀 찾아줘',
  '디자인에 관심 있는 사람 찾아줘',
];

const roles = [
  { value: '개발', words: /개발자|개발/, explicit: /개발자|개발역할|역할개발/ },
  {
    value: '디자인',
    words: /디자이너|디자인/,
    explicit: /디자이너|디자인역할|역할디자인/,
  },
  { value: '기획', words: /기획자|기획/, explicit: /기획자|기획역할|역할기획/ },
  { value: '자료조사', words: /자료조사/, explicit: /자료조사/ },
  { value: '발표', words: /발표자|발표/, explicit: /발표/ },
  { value: '마케팅', words: /마케터|마케팅/, explicit: /마케터|마케팅/ },
];

function normalize(value: string) {
  return value.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, '');
}

function clarification(text: string, search: ChatSearchState): ChatReply {
  return {
    text,
    recommendations: [],
    suggestions: [...startingQuestions],
    search,
  };
}

function suggestionsFor(kind: ChatSearchState['kind']) {
  if (kind === 'contests') {
    return ['마감 빠른 순으로', '디자인 공모전 찾아줘', '공모전 전체 보기'];
  }
  if (kind === 'teams') {
    return ['개발 역할만', '디자인 역할만', '팀 전체 보기'];
  }
  return ['개발 역할만', '디자인에 관심 있는 사람 찾아줘', '사람 전체 보기'];
}

// A small explicit demo vocabulary prevents unknown requirements from silently
// becoming an unfiltered recommendation. This is not an AI or scoring engine.
function hasUnknownWords(message: string) {
  return Boolean(
    message
      .replace(/공모전|팀원|사람|팀/g, '')
      .replace(
        /개발자|개발|디자이너|디자인|기획자|기획|자료조사|발표자|발표|마케터|마케팅/g,
        '',
      )
      .replace(/아이디어|it·기술|it기술|기술|it|친환경|환경|그린테크/g, '')
      .replace(
        /찾아주세요|찾아줘|찾아보기|찾기|추천해주세요|추천해줘|추천해|추천|보여주세요|보여줘|보고싶어요|보고싶어|알려주세요|알려줘|골라줘|검색해줘|검색|보기/g,
        '',
      )
      .replace(
        /모집중인|모집중|모집하는|모집|관심이있는|관심있는|관심|관련된|관련|분야|희망역할|역할|조건|마감일|마감|빠른순으로|빠른순|임박순|가까운|임박한|임박|빠른|이른|가장|순으로|순|전체|모든|전부|초기화|처음부터|다시|있는/g,
        '',
      )
      .replace(
        /에서|으로|에게|하고|이랑|과|와|의|에|이|가|을|를|만|중|도|는|은|요/g,
        '',
      )
      .replace(/[^\p{L}\p{N}]/gu, ''),
  );
}

function contestText(contest: Contest) {
  return normalize(
    `${contest.title} ${contest.organizer} ${contest.description} ${contest.interests.join(' · ')}`,
  );
}

function deadlineKey(contest: Contest | undefined) {
  return contest ? contestDeadline(contest) : Infinity;
}

// [출처 2, 3] 예시 데이터 기반 로컬 응답
export function createDemoReply(
  message: string,
  previous: ChatSearchState | undefined,
  data: SearchData,
): ChatReply {
  const query = normalize(message);
  const more =
    /^(?:다른추천도|다른결과도|더|추가로|계속)(?:보여줘|추천해줘|찾아줘)?$/.test(
      query,
    );
  const unchanged = { ...(previous ?? { kind: 'contests' as const }) };

  if (/모집마감|모집종료|마감된|마감이지난|마감지난|종료된/.test(query)) {
    return clarification(
      '접수 중인 공모전과 모집 중인 팀을 찾아드려요. 접수 마감 공고와 모집이 끝난 팀은 추천에서 제외하며, 등록된 공모전 마감일 순으로 찾아볼 수 있어요.',
      unchanged,
    );
  }

  if (
    /연락처|이메일|전화|카카오|카톡|개인정보|비공개|지원자|지원내역|비밀번호|패스워드|인증정보|로그인정보/.test(
      query,
    )
  ) {
    return clarification(
      '연락처·로그인 정보·비공개 프로필·지원자 정보는 AI 탐색에서 제공하지 않아요. 공개 프로필의 역할과 관심 분야로 찾아볼 수 있어요.',
      unchanged,
    );
  }
  if (/포트폴리오|주말|평일|요일|오전|오후|야간|시간|일정/.test(query)) {
    return clarification(
      '공개 프로필의 주당 참여 가능 시간(전체 프로젝트 합산)과 포트폴리오는 프로필 상세에서 확인할 수 있어요. 현재 채팅에서는 시간 조건 검색·외부 포트폴리오 분석·일정 추정을 지원하지 않아요. 역할이나 관심 분야로 사람을 찾아볼 수 있어요.',
      unchanged,
    );
  }
  if (/실력|최고|잘하는|능력|역량|경력|경험|수상|자격|학년|전공/.test(query)) {
    return clarification(
      '등록한 학력·역량·경험은 공개 프로필 상세에서 확인할 수 있어요. 실력이나 참여 가능 여부를 추정하지 않으며, 현재 채팅은 역할·관심 분야·공모전 마감일로 찾아볼 수 있어요.',
      unchanged,
    );
  }

  const kinds: ChatSearchState['kind'][] = [];
  if (/공모전/.test(query)) kinds.push('contests');
  if (/팀/.test(query.replace(/팀원/g, ''))) kinds.push('teams');
  if (/사람|팀원/.test(query)) kinds.push('people');
  if (kinds.length > 1) {
    return clarification(
      '공모전, 모집 팀, 공개된 사람 프로필 중 어떤 대상을 찾을지 하나만 알려주세요.',
      unchanged,
    );
  }

  const deadlineFirst =
    /마감.*(?:가까운|빠른|임박|이른|순)|(?:빠른|가까운|임박한|이른).*마감/.test(
      query,
    );
  const reset = /전체|모든|전부|초기화|처음부터/.test(query);
  const explicitKind = kinds[0];
  const kind = explicitKind ?? previous?.kind ?? 'contests';
  const categoryContext = kind === 'contests' || /관심|분야/.test(query);
  const matchedRoles = roles.filter(
    (role) =>
      role.words.test(query) && (!categoryContext || role.explicit.test(query)),
  );
  const categories: string[] = [];
  if (/아이디어/.test(query) || (categoryContext && /기획/.test(query)))
    categories.push('교육');
  if (/it|기술/.test(query)) categories.push('IT·기술');
  if (categoryContext && /디자인/.test(query)) categories.push('디자인');
  const keyword = /환경|그린테크/.test(query) ? '환경' : undefined;
  const unhandledRole = roles.some(
    (role) =>
      role.words.test(query) &&
      !matchedRoles.includes(role) &&
      !(role.value === '기획' && categories.includes('교육')) &&
      !(role.value === '디자인' && categories.includes('디자인')),
  );

  if (matchedRoles.length > 1 || categories.length > 1) {
    return clarification(
      '한 번에 하나의 역할과 하나의 관심 분야로 찾아볼 수 있어요. 원하는 조건을 하나씩 알려주세요.',
      unchanged,
    );
  }
  if (
    (!more && hasUnknownWords(query)) ||
    unhandledRole ||
    (!explicitKind && !previous && !deadlineFirst) ||
    (!explicitKind &&
      !matchedRoles.length &&
      !categories.length &&
      !keyword &&
      !deadlineFirst &&
      !reset &&
      !more)
  ) {
    return clarification(
      '공개된 공모전, 모집 팀, 사람을 역할·관심 분야·마감일로 찾아볼 수 있어요. 아래 질문을 선택하거나 찾을 대상과 조건을 알려주세요.',
      unchanged,
    );
  }
  if (kind === 'contests' && matchedRoles.length) {
    return clarification(
      '공모전에는 모집 역할 정보가 없어요. 공모전 분야로 찾거나, 그 역할을 모집하는 팀을 찾아볼 수 있어요.',
      unchanged,
    );
  }
  if (kind === 'people' && deadlineFirst) {
    return clarification(
      '사람 프로필에는 마감일이 없어요. 공개한 역할이나 관심 분야로 찾아볼 수 있어요.',
      unchanged,
    );
  }

  const search: ChatSearchState =
    reset || (explicitKind && explicitKind !== previous?.kind)
      ? { kind }
      : { ...unchanged, kind };
  if (matchedRoles[0]) search.role = matchedRoles[0].value;
  if (categories[0]) search.category = categories[0];
  if (keyword) search.keyword = keyword;
  if (deadlineFirst) search.deadlineFirst = true;

  const recommendations: ChatRecommendation[] = [];
  if (kind === 'contests') {
    const matches = data.contests.filter(
      (contest) =>
        isContestOpen(contest) &&
        (!search.category || contest.interests.includes(search.category)) &&
        (!search.keyword ||
          contestText(contest).includes(normalize(search.keyword))),
    );
    if (search.deadlineFirst)
      matches.sort((a, b) => deadlineKey(a) - deadlineKey(b));
    for (const contest of matches) {
      const reasons = [`${contest.interests.join(' · ')} 분야 공모전이에요.`];
      if (search.keyword)
        reasons.push(
          `공개된 공모전 정보에 ‘${search.keyword}’이 포함되어 있어요.`,
        );
      reasons.push(`등록된 마감일은 ${deadlineLabel(contest)}이에요.`);
      recommendations.push({
        kind: 'contest',
        id: contest.id,
        reason: reasons.join(' '),
      });
    }
  } else if (kind === 'teams') {
    const contestById = new Map(
      data.contests.map((contest) => [contest.id, contest]),
    );
    const matches = data.teams.filter((team) => {
      const contest = contestById.get(team.contestId);
      const searchable =
        normalize(`${team.name} ${team.summary}`) +
        (contest ? contestText(contest) : '');
      return (
        availableTeam(team, data) &&
        (!search.role || team.roles.includes(search.role)) &&
        (!search.category || contest?.interests.includes(search.category)) &&
        (!search.keyword || searchable.includes(normalize(search.keyword)))
      );
    });
    if (search.deadlineFirst)
      matches.sort(
        (a, b) =>
          deadlineKey(contestById.get(a.contestId)) -
          deadlineKey(contestById.get(b.contestId)),
      );
    for (const team of matches) {
      const reasons = [
        search.role
          ? `‘${search.role}’ 역할을 모집하고 있어요.`
          : '현재 모집 중인 팀이에요.',
      ];
      if (search.category)
        reasons.push(`참여 공모전이 ${search.category} 분야예요.`);
      if (search.keyword)
        reasons.push(
          `공개된 팀·참여 공모전 정보에 ‘${search.keyword}’이 포함되어 있어요.`,
        );
      const contest = contestById.get(team.contestId);
      if (search.deadlineFirst && contest)
        reasons.push(`참여 공모전 마감일은 ${deadlineLabel(contest)}이에요.`);
      recommendations.push({
        kind: 'team',
        id: team.id,
        reason: reasons.join(' '),
      });
    }
  } else {
    for (const person of data.people) {
      const searchable = normalize((person.interests ?? []).join(' '));
      if (
        (search.role && !person.roles.includes(search.role)) ||
        (search.category && !person.interests?.includes(search.category)) ||
        (search.keyword && !searchable.includes(normalize(search.keyword)))
      )
        continue;
      const reasons: string[] = [];
      if (search.role) reasons.push(`희망 역할 ‘${search.role}’을 공개했어요.`);
      if (search.category)
        reasons.push(`관심 분야 ‘${search.category}’을 공개했어요.`);
      if (search.keyword)
        reasons.push(
          `공개한 관심 분야에 ‘${search.keyword}’이 포함되어 있어요.`,
        );
      if (!reasons.length) reasons.push('탐색에 공개된 사람 프로필이에요.');
      recommendations.push({
        kind: 'person',
        id: person.id,
        reason: reasons.join(' '),
      });
    }
  }

  const label =
    kind === 'contests'
      ? '공모전'
      : kind === 'teams'
        ? '모집 팀'
        : '사람 프로필';
  const alreadyShown = more ? (previous?.shownIds ?? []) : [];
  const remaining = recommendations.filter(
    (item) => !alreadyShown.includes(`${item.kind}:${item.id}`),
  );
  const visible = remaining.slice(0, 3);
  search.shownIds = [
    ...alreadyShown,
    ...visible.map((item) => `${item.kind}:${item.id}`),
  ];
  const countText =
    remaining.length > 3
      ? `${remaining.length}개 중 3개`
      : `${visible.length}개`;
  const orderText = search.deadlineFirst
    ? ' 등록된 공모전 마감일이 빠른 순서예요.'
    : '';
  return {
    text: visible.length
      ? `현재 목록에서 조건에 맞는 ${label} ${countText}를 찾았어요.${orderText}`
      : more
        ? `이 조건으로 더 보여드릴 ${label}이 없어요. 다른 조건으로 다시 찾아볼 수 있어요.`
        : `현재 목록에는 이 조건과 일치하는 ${label}이 없어요. 전체 보기로 조건을 지우거나 다른 조건을 선택해 주세요.`,
    recommendations: visible,
    suggestions:
      remaining.length > 3
        ? ['다른 추천도 보여줘', ...suggestionsFor(kind).slice(0, 2)]
        : suggestionsFor(kind),
    search,
  };
}

/** Re-check mutable visibility and availability before displaying or copying a past card. */
// [출처 3] 이전 카드도 현재 공개 범위·모집 상태로 다시 확인
export function currentRecommendation(
  item: ChatRecommendation,
  data: SearchData,
) {
  if (item.kind === 'person') {
    const person = data.people.find((value) => value.id === item.id);
    return person
      ? {
          title: person.name,
          reason: `희망 역할: ${person.roles.join(' · ')}.${person.interests?.length ? ` 공개한 관심 분야: ${person.interests.join(' · ')}.` : ''}`,
        }
      : null;
  }
  const contest = data.contests.find((value) => value.id === item.id);
  if (item.kind === 'contest')
    return contest && isContestOpen(contest)
      ? { title: contest.title, reason: item.reason }
      : null;
  const team = data.teams.find((value) => value.id === item.id);
  if (!team || !availableTeam(team, data)) return null;
  return {
    title: team.name,
    reason: `현재 ${team.roles.join(' · ')} 역할을 모집하고 있어요. ${team.members}/${team.capacity}명 · ${team.recruitmentDeadline} 마감.`,
  };
}
