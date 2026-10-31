/** 기본 응답 호환성과 rich 결과의 서버 사실 계약을 검증합니다. */
import { describe, expect, it } from 'vitest';
import { ChatStart, ResourceCard } from './contract';

const card = {
  kind: 'person',
  resourceId: '11111111-1111-4111-8111-111111111111',
  title: '공개 사용자',
  reason: '등록 조건 참고',
  fieldCodes: ['it'],
  roleCodes: ['development'],
  isDemo: false,
};
const rich = {
  ...card,
  evidence: ['등록된 개발 경험'],
  details: {
    kind: 'person',
    skillCodes: ['programming'],
    weeklyAvailabilityCode: null,
    experienceState: 'unspecified',
    experienceBody: null,
    introduction: null,
  },
};

describe('일반 대화의 선택적 rich 결과', () => {
  it('preserves a legacy input and card exactly, without implicit fields', () => {
    const input = {
      requestId: card.resourceId,
      conversationId: card.resourceId,
      clientMessageId: card.resourceId,
      content: '사람 찾아줘',
      history: [],
      previousResults: [],
    };
    expect(ChatStart.parse(input)).toEqual(input);
    expect(ChatStart.parse({ ...input, resultFormat: 'rich' })).toEqual({
      ...input,
      resultFormat: 'rich',
    });
    expect(ResourceCard.parse(card)).toEqual(card);
    expect(ResourceCard.parse(rich)).toEqual(rich);
  });

  it.each([
    { ...card, evidence: [] },
    { ...card, details: rich.details },
    { ...rich, kind: 'team' },
    { ...rich, details: { ...rich.details, skillCodes: ['invented'] } },
    { ...rich, details: { ...rich.details, privateToken: 'secret' } },
    { ...rich, evidence: Array(7).fill('근거') },
    { ...rich, evidence: ['가'.repeat(501)] },
    { ...rich, score: 85 },
  ])('rejects incomplete or unregistered rich data: %j', (value) => {
    expect(ResourceCard.safeParse(value).success).toBe(false);
  });
});
