import { describe, expect, it } from 'vitest';
import {
  createDemoReply,
  currentRecommendation,
} from '@/features/ai/chat-demo';
import type { Application } from '@/features/applications/api';
import type { Profile } from '@/features/profiles/api';
import {
  contests,
  getPublicProfile,
  initialProfile,
  initialTeams,
  people,
} from '@/features/demo/data';
import {
  demoIds,
  fixtureAcademicUnits,
  fixtureCatalogs,
} from '@/features/demo/fixtures';
import { createLabels } from '@/features/catalogs/labels';

const ME = demoIds.accounts.me;
// 기본 데이터에서는 본인이 어느 팀에도 소속되지 않은 것으로 봅니다(memberTeamIds 비움).
const availableTeams = initialTeams;
// 코드 표시명은 GET /catalogs 응답(목업)과 같은 선택지로 만듭니다.
const labels = createLabels(fixtureCatalogs(), fixtureAcademicUnits());
const data = {
  contests,
  teams: availableTeams,
  people,
  labels,
  accountId: ME,
  memberTeamIds: [] as string[],
};

describe('createDemoReply', () => {
  it('matches an actual recruiting role and excludes closed teams even when their role matches', () => {
    const reply = createDemoReply('개발자를 모집하는 팀 찾아줘', undefined, {
      ...data,
      teams: [
        ...availableTeams,
        {
          ...availableTeams[1]!,
          id: 'closed-dev',
          recruitmentState: 'closed' as const,
        },
      ],
    });
    expect(reply.search).toMatchObject({ kind: 'teams', role: 'development' });
    expect(reply.recommendations).toEqual([
      {
        kind: 'team',
        id: demoIds.teams.greenwave,
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
    expect(reply.search).toMatchObject({
      kind: 'contests',
      deadlineFirst: true,
    });
    expect(reply.recommendations.map((result) => result.id)).toEqual([
      demoIds.contests.green,
      demoIds.contests.campus,
      demoIds.contests.local,
    ]);
    expect(reply.recommendations[0]?.reason).toContain('2026.10.25');
    expect(JSON.stringify(reply)).not.toMatch(/적합도|점수|%|참여할 수/);
    expect(JSON.stringify(data)).toBe(before);
  });

  it('uses registered interests rather than guessing an interest from a role and adds follow-up role constraints', () => {
    const noInterest: Profile = {
      ...people[0]!,
      accountId: 'no-interest',
      realName: '관심 분야 미입력',
      roleCodes: ['design'],
      fieldCodes: [],
      introduction: '디자인을 좋아합니다.',
    };
    const first = createDemoReply('디자인에 관심 있는 사람 찾아줘', undefined, {
      ...data,
      people: [...people, noInterest],
    });
    expect(first.search).toMatchObject({ kind: 'people', category: 'design' });
    expect(first.recommendations.map((result) => result.id)).toEqual([
      demoIds.accounts.doyun,
      demoIds.accounts.sua,
    ]);
    const next = createDemoReply('개발 역할만', first.search, data);
    expect(next.search).toMatchObject({
      kind: 'people',
      category: 'design',
      role: 'development',
    });
    expect(next.recommendations.map((result) => result.id)).toEqual([
      demoIds.accounts.doyun,
    ]);
    expect(next.recommendations[0]?.reason).toContain('희망 역할 ‘개발’');
    expect(first.search).not.toHaveProperty('role');
  });

  it('keeps a topic when sorting a follow-up and clears stale filters for another kind or explicit all', () => {
    const first = createDemoReply('환경 공모전 찾아줘', undefined, data);
    expect(first.search).toMatchObject({ kind: 'contests', keyword: '환경' });
    expect(first.recommendations.map((result) => result.id)).toEqual([
      demoIds.contests.green,
    ]);
    const sorted = createDemoReply('마감 빠른 순으로', first.search, data);
    expect(sorted.search).toMatchObject({
      kind: 'contests',
      keyword: '환경',
      deadlineFirst: true,
    });
    const changed = createDemoReply(
      '디자인에 관심 있는 사람 찾아줘',
      sorted.search,
      data,
    );
    expect(changed.search).toMatchObject({
      kind: 'people',
      category: 'design',
    });
    const all = createDemoReply('공모전 전체 보기', sorted.search, data);
    expect(all.search).toMatchObject({ kind: 'contests' });
    expect(all.search).not.toHaveProperty('keyword');
    expect(all.search).not.toHaveProperty('deadlineFirst');
    expect(all.recommendations.map((result) => result.id)).toEqual([
      demoIds.contests.campus,
      demoIds.contests.green,
      demoIds.contests.local,
    ]);
  });

  it('limits results to three while explaining the full match count', () => {
    const reply = createDemoReply('개발 팀 찾아줘', undefined, {
      ...data,
      teams: Array.from({ length: 5 }, (_, index) => ({
        ...availableTeams[1]!,
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

  it('returns up to three unseen results on each additional request and reports exhaustion', () => {
    const expanded = {
      ...data,
      teams: Array.from({ length: 7 }, (_, index) => ({
        ...availableTeams[1]!,
        id: `team-${index}`,
      })),
    };
    const first = createDemoReply('개발 팀 찾아줘', undefined, expanded);
    const second = createDemoReply(
      '다른 추천도 보여줘',
      first.search,
      expanded,
    );
    const third = createDemoReply('더 보여줘', second.search, expanded);
    const empty = createDemoReply('추가로 보여줘', third.search, expanded);
    expect(
      [first, second, third, empty].map(
        (reply) => reply.recommendations.length,
      ),
    ).toEqual([3, 3, 1, 0]);
    const ids = [first, second, third].flatMap((reply) =>
      reply.recommendations.map((item) => item.id),
    );
    expect(new Set(ids).size).toBe(7);
    expect(first.suggestions).toContain('다른 추천도 보여줘');
    expect(empty.text).toContain('더 보여드릴 모집 팀이 없어요');
    const reset = createDemoReply('팀 전체 보기', empty.search, expanded);
    expect(reset.recommendations.map((item) => item.id)).toEqual(
      first.recommendations.map((item) => item.id),
    );
  });

  it('matches any registered contest category, including a second category', () => {
    const reply = createDemoReply('기술 공모전 찾아줘', undefined, data);
    expect(reply.recommendations.map((item) => item.id)).toEqual(
      expect.arrayContaining([demoIds.contests.campus, demoIds.contests.green]),
    );
    expect(
      reply.recommendations.some((item) => item.id === demoIds.contests.local),
    ).toBe(false);
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
      const previous = { kind: 'teams' as const, role: 'development' };
      const reply = createDemoReply(message, previous, data);
      expect(reply.recommendations).toEqual([]);
      expect(reply.search).toMatchObject(previous);
      expect(reply.suggestions).toContain('마감이 가까운 공모전 찾아줘');
    },
  );

  it.each([
    '개발자 연락처 알려줘',
    '비공개 프로필 찾아줘',
    '지원자 정보 알려줘',
    '로그인 비밀번호 알려줘',
  ])(
    'does not expose restricted account or applicant information: %s',
    (message) => {
      const reply = createDemoReply(message, undefined, data);
      expect(reply.recommendations).toEqual([]);
      expect(reply.text).toContain('AI 탐색에서 제공하지 않아요');
      expect(JSON.stringify(reply)).not.toContain('김서연');
      expect(JSON.stringify(reply)).not.toContain(demoIds.teams.greenwave);
    },
  );

  it.each(['주말 가능한 사람 찾아줘', '포트폴리오가 좋은 사람 추천해줘'])(
    'distinguishes public profile details from unsupported analysis: %s',
    (message) => {
      const previous = { kind: 'people' as const, role: 'development' };
      const reply = createDemoReply(message, previous, data);
      expect(reply.recommendations).toEqual([]);
      expect(reply.search).toMatchObject(previous);
      expect(reply.text).toContain(
        '공개 프로필의 주당 참여 가능 시간(전체 프로젝트 합산)과 포트폴리오는 프로필 상세에서 확인할 수 있어요',
      );
      expect(reply.text).toContain(
        '시간 조건 검색·외부 포트폴리오 분석·일정 추정을 지원하지 않아요',
      );
      expect(reply.suggestions).toContain('디자인에 관심 있는 사람 찾아줘');
    },
  );

  it('does not infer skills or participation eligibility from public profile details', () => {
    const reply = createDemoReply(
      '최고의 실력을 가진 팀원 찾아줘',
      undefined,
      data,
    );
    expect(reply.recommendations).toEqual([]);
    expect(reply.text).toContain('실력이나 참여 가능 여부를 추정하지 않으며');
  });

  it('returns an empty state for a supported but unmatched role without substituting unrelated candidates', () => {
    const reply = createDemoReply(
      '발표자를 모집하는 팀 찾아줘',
      undefined,
      data,
    );
    expect(reply.search).toMatchObject({ kind: 'teams', role: 'presentation' });
    expect(reply.recommendations).toEqual([]);
    expect(reply.text).toContain('일치하는 모집 팀이 없어요');
    expect(reply.suggestions).toContain('팀 전체 보기');
  });
});

describe('current recommendation availability', () => {
  it('excludes expired recruiting teams and closed contest candidates', () => {
    // 기한이 지난 팀은 서버가 isRecruiting=false로 응답합니다(docs/api/teams.md#values).
    const expired = {
      ...availableTeams[1]!,
      recruitmentEndsAt: '2026-10-17T15:00:00Z',
      isRecruiting: false,
    };
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
  it('removes past team cards after capacity fills', () => {
    const full = {
      ...availableTeams[1]!,
      memberCount: Number(initialTeams[1]!.capacity),
    };
    expect(
      currentRecommendation(
        { kind: 'team', id: full.id, reason: '모집 중' },
        { ...data, teams: [full] },
      ),
    ).toBeNull();
  });
  it('excludes owned, joined and already-applied teams from new and past cards but allows a different team in the same contest', () => {
    const candidate = availableTeams[1]!;
    const card = { kind: 'team' as const, id: candidate.id, reason: '모집 중' };
    // 팀장으로 소유한 팀, 팀원으로 소속된 팀 모두 본인 소속 팀(memberTeamIds)으로 제외
    for (const team of [
      { ...candidate, ownerAccountId: ME },
      { ...candidate, memberCount: candidate.memberCount + 1 },
    ]) {
      const ownData = { ...data, teams: [team], memberTeamIds: [team.id] };
      expect(
        createDemoReply('개발 팀 찾아줘', undefined, ownData).recommendations,
      ).toEqual([]);
      expect(currentRecommendation(card, ownData)).toBeNull();
    }
    const appliedData = {
      ...data,
      applications: [
        {
          id: 'current',
          version: '1',
          teamId: candidate.id,
          contestId: candidate.contestId,
          applicantAccountId: ME,
          roleCode: 'development',
          message: null,
          status: 'submitted',
          discardReason: null,
          discardedByApplicationId: null,
          discardedByTeamId: null,
          submittedAt: '2026-10-18T00:00:00Z',
          updatedAt: '2026-10-18T00:00:00Z',
        },
      ] as Application[],
    };
    expect(
      createDemoReply('개발 팀 찾아줘', undefined, appliedData).recommendations,
    ).toEqual([]);
    expect(currentRecommendation(card, appliedData)).toBeNull();
    const cancelledData = {
      ...appliedData,
      applications: appliedData.applications.map((item) => ({
        ...item,
        status: 'canceled' as const,
      })),
    };
    expect(currentRecommendation(card, cancelledData)).not.toBeNull();
    const sameContest = {
      ...data,
      teams: [{ ...candidate, id: 'another-team' }, candidate],
      memberTeamIds: ['another-team'],
    };
    expect(
      createDemoReply(
        '개발 팀 찾아줘',
        undefined,
        sameContest,
      ).recommendations.map((item) => item.id),
    ).toEqual([candidate.id]);
  });

  it('excludes globally private profiles from new recommendations and previously generated cards', () => {
    const profile = {
      ...initialProfile,
      experienceState: 'provided' as const,
      experienceBody: '공개 프로젝트 경험',
      weeklyAvailabilityCode: 'under_5',
      portfolio: { url: 'https://example.com/portfolio', title: null },
      isPublic: true,
    };
    const person = getPublicProfile(profile)!;
    const publicData = { ...data, people: [person] };
    const reply = createDemoReply('사람 전체 보기', undefined, publicData);
    expect(reply.recommendations).toHaveLength(1);
    const card = reply.recommendations[0]!;
    expect(card.id).toBe(demoIds.accounts.me);
    expect(currentRecommendation(card, publicData)?.title).toBe(
      profile.realName,
    );

    const hidden = getPublicProfile({
      ...profile,
      isPublic: false,
    });
    const privateData = { ...data, people: hidden ? [hidden] : [] };
    expect(
      createDemoReply('사람 전체 보기', undefined, privateData).recommendations,
    ).toEqual([]);
    expect(currentRecommendation(card, privateData)).toBeNull();
  });
});
