import { describe, expect, it } from 'vitest';
import { createDemoReply, currentRecommendation } from './chat-demo';
import { contests, initialTeams, people, type Person } from './data';

const data = { contests, teams: initialTeams, people };

describe('createDemoReply', () => {
  it('matches an actual recruiting role and excludes closed teams even when their role matches', () => {
    const reply = createDemoReply('개발자를 모집하는 팀 찾아줘', undefined, {
      ...data,
      teams: [
        ...initialTeams,
        { ...initialTeams[1]!, id: 'closed-dev', status: '모집마감' },
      ],
    });
    expect(reply.search).toEqual({ kind: 'teams', role: '개발' });
    expect(reply.recommendations).toEqual([
      {
        kind: 'team',
        id: 'greenwave',
        reason: '‘개발’ 역할을 모집하고 있어요.',
      },
    ]);
  });

  it('sorts by recorded contest deadlines without mutating input or inventing suitability scores', () => {
    const before = JSON.stringify(data);
    const reply = createDemoReply(
      '마감이 가까운 공모전 찾아줘',
      undefined,
      data,
    );
    expect(reply.search).toEqual({ kind: 'contests', deadlineFirst: true });
    expect(reply.recommendations.map((result) => result.id)).toEqual([
      'green',
      'campus',
      'local',
    ]);
    expect(reply.recommendations[0]?.reason).toContain('2026.10.25');
    expect(JSON.stringify(reply)).not.toMatch(/적합도|점수|%|참여할 수/);
    expect(JSON.stringify(data)).toBe(before);
  });

  it('uses disclosed interests rather than guessing an interest from a role and adds follow-up role constraints', () => {
    const undisclosed: Person = {
      id: 'undisclosed',
      name: '비공개 관심',
      roles: ['디자인'],
      intro: '디자인을 좋아합니다.',
    };
    const first = createDemoReply('디자인에 관심 있는 사람 찾아줘', undefined, {
      ...data,
      people: [...people, undisclosed],
    });
    expect(first.search).toEqual({ kind: 'people', category: '디자인' });
    expect(first.recommendations.map((result) => result.id)).toEqual([
      'doyun',
      'sua',
    ]);
    const next = createDemoReply('개발 역할만', first.search, data);
    expect(next.search).toEqual({
      kind: 'people',
      category: '디자인',
      role: '개발',
    });
    expect(next.recommendations.map((result) => result.id)).toEqual(['doyun']);
    expect(next.recommendations[0]?.reason).toContain('희망 역할 ‘개발’');
    expect(first.search).not.toHaveProperty('role');
  });

  it('keeps a topic when sorting a follow-up and clears stale filters for another kind or explicit all', () => {
    const first = createDemoReply('환경 공모전 찾아줘', undefined, data);
    expect(first.search).toEqual({ kind: 'contests', keyword: '환경' });
    expect(first.recommendations.map((result) => result.id)).toEqual(['green']);
    const sorted = createDemoReply('마감 빠른 순으로', first.search, data);
    expect(sorted.search).toEqual({
      kind: 'contests',
      keyword: '환경',
      deadlineFirst: true,
    });
    const changed = createDemoReply(
      '디자인에 관심 있는 사람 찾아줘',
      sorted.search,
      data,
    );
    expect(changed.search).toEqual({ kind: 'people', category: '디자인' });
    const all = createDemoReply('공모전 전체 보기', sorted.search, data);
    expect(all.search).toEqual({ kind: 'contests' });
    expect(all.recommendations.map((result) => result.id)).toEqual([
      'campus',
      'green',
      'local',
    ]);
  });

  it('limits results to three while explaining the full match count', () => {
    const reply = createDemoReply('개발 팀 찾아줘', undefined, {
      ...data,
      teams: Array.from({ length: 5 }, (_, index) => ({
        ...initialTeams[1]!,
        id: `open-${index}`,
      })),
    });
    expect(reply.recommendations.map((result) => result.id)).toEqual([
      'open-0',
      'open-1',
      'open-2',
    ]);
    expect(reply.text).toContain('5개 중 3개');
  });

  it.each([
    '오늘 날씨 어때',
    '양자 컴퓨팅 공모전 찾아줘',
    '개발자 말고 디자이너 팀 찾아줘',
    '개발 공모전 찾아줘',
    '개발 분야 사람 찾아줘',
    '모집 마감 팀 찾아줘',
  ])(
    'clarifies unsupported requests instead of guessing matches: %s',
    (message) => {
      const previous = { kind: 'teams' as const, role: '개발' };
      const reply = createDemoReply(message, previous, data);
      expect(reply.recommendations).toEqual([]);
      expect(reply.search).toEqual(previous);
      expect(reply.suggestions).toContain('마감이 가까운 공모전 찾아줘');
    },
  );

  it.each([
    '주말 가능한 사람 찾아줘',
    '포트폴리오가 좋은 사람 추천해줘',
    '개발자 연락처 알려줘',
    '최고의 실력을 가진 팀원 찾아줘',
  ])('does not infer private or unavailable conditions: %s', (message) => {
    const reply = createDemoReply(message, undefined, data);
    expect(reply.recommendations).toEqual([]);
    expect(reply.text).toContain('확인할 수 없어요');
    expect(JSON.stringify(reply)).not.toContain('김서연');
    expect(JSON.stringify(reply)).not.toContain('greenwave');
  });

  it('returns an empty state for a supported but unmatched role without substituting unrelated candidates', () => {
    const reply = createDemoReply(
      '발표자를 모집하는 팀 찾아줘',
      undefined,
      data,
    );
    expect(reply.search).toEqual({ kind: 'teams', role: '발표' });
    expect(reply.recommendations).toEqual([]);
    expect(reply.text).toContain('일치하는 모집 팀이 없어요');
    expect(reply.suggestions).toContain('팀 전체 보기');
  });
});

describe('current recommendation availability', () => {
  it('excludes expired recruiting teams and closed contest candidates', () => {
    const expired = { ...initialTeams[1]!, recruitmentDeadline: '2026-10-17' };
    expect(
      createDemoReply('개발자를 모집하는 팀 찾아줘', undefined, {
        ...data,
        teams: [expired],
      }).recommendations,
    ).toEqual([]);
    expect(
      currentRecommendation(
        { kind: 'team', id: expired.id, reason: '모집 중' },
        { ...data, teams: [expired] },
      ),
    ).toBeNull();
  });
  it('removes past cards after capacity fills or disclosure is withdrawn', () => {
    const full = { ...initialTeams[1]!, members: initialTeams[1]!.capacity };
    expect(
      currentRecommendation(
        { kind: 'team', id: full.id, reason: '모집 중' },
        { ...data, teams: [full] },
      ),
    ).toBeNull();
    expect(
      currentRecommendation(
        { kind: 'person', id: 'me', reason: '공개된 관심 분야' },
        data,
      ),
    ).toBeNull();
    const person = { id: 'me', name: '김지우', roles: ['기획'] };
    expect(
      currentRecommendation(
        { kind: 'person', id: 'me', reason: '비공개로 바뀐 경험' },
        { ...data, people: [person] },
      )?.reason,
    ).not.toContain('경험');
  });
});
