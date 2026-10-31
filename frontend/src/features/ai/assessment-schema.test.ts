/** 지원자 평가의 완전성·근거와 비스트리밍 완료 응답 계약을 검증합니다. */
import { describe, expect, it } from 'vitest';
import {
  ApplicantAssessment,
  ApplicantCompletion,
  AssessmentCriterion,
  ApplicantProfileFacts,
} from './contract';

const assessment = {
  criteria: ['role', 'skills', 'experience', 'availability'].map((key) => ({
    key,
    score: null,
    informationStatus: 'insufficient',
    summary: '추가 정보가 필요해요.',
    evidence: [],
  })),
  questions: ['맡고 싶은 작업을 알려 주세요.'],
};

describe('지원자 평가 계약', () => {
  it('limits recommendation skill facts to the server catalog and rejects extra profile details', () => {
    expect(
      ApplicantProfileFacts.safeParse({ skillCodes: ['programming'] }).success,
    ).toBe(true);
    expect(
      ApplicantProfileFacts.safeParse({ skillCodes: ['invented_skill'] })
        .success,
    ).toBe(false);
    expect(
      ApplicantProfileFacts.safeParse({
        skillCodes: Array(14).fill('programming'),
      }).success,
    ).toBe(false);
    expect(
      ApplicantProfileFacts.safeParse({
        skillCodes: [],
        introduction: '추가 개인정보',
      }).success,
    ).toBe(false);
  });
  it('requires all four distinct criteria without a combined score', () => {
    expect(ApplicantAssessment.safeParse(assessment).success).toBe(true);
    expect(
      ApplicantAssessment.safeParse({
        ...assessment,
        criteria: assessment.criteria.slice(1),
      }).success,
    ).toBe(false);
    expect(
      ApplicantAssessment.safeParse({
        ...assessment,
        criteria: Array(4).fill(assessment.criteria[0]),
      }).success,
    ).toBe(false);
    expect(
      ApplicantAssessment.safeParse({ ...assessment, score: 90 }).success,
    ).toBe(false);
  });
  it.each([0, 5, 45, 100])(
    'accepts a supported five-point score of %s',
    (score) => {
      expect(
        AssessmentCriterion.safeParse({
          ...assessment.criteria[0],
          score,
          informationStatus: 'sufficient',
          evidence: [{ source: 'application.role', text: '기획자' }],
        }).success,
      ).toBe(true);
    },
  );
  it.each([-5, 101, 105, 2.5, 7, '50'])(
    'rejects an invalid score of %s',
    (score) => {
      expect(
        AssessmentCriterion.safeParse({
          ...assessment.criteria[0],
          score,
          informationStatus: 'sufficient',
          evidence: [{ source: 'application.role', text: '기획자' }],
        }).success,
      ).toBe(false);
    },
  );
  it.each([
    { score: null, informationStatus: 'sufficient' },
    { score: 0, informationStatus: 'insufficient' },
    { score: 50, informationStatus: 'insufficient' },
  ])('rejects a score/status contradiction: %j', (fields) => {
    expect(
      AssessmentCriterion.safeParse({
        ...assessment.criteria[0],
        ...fields,
        evidence: [{ source: 'application.role', text: '기획자' }],
      }).success,
    ).toBe(false);
  });
  it('rejects the old state field', () => {
    expect(
      AssessmentCriterion.safeParse({
        ...assessment.criteria[0],
        state: 'insufficient_information',
      }).success,
    ).toBe(false);
  });
  it('requires evidence for a numeric score and rejects unknown sources', () => {
    const criteria = assessment.criteria.map((item, index) =>
      index ? item : { ...item, score: 50, informationStatus: 'sufficient' },
    );
    expect(
      ApplicantAssessment.safeParse({ ...assessment, criteria }).success,
    ).toBe(false);
    criteria[0] = {
      ...criteria[0]!,
      evidence: [{ source: 'external.portfolio', text: '추정 역량' }],
    } as (typeof criteria)[number];
    expect(
      ApplicantAssessment.safeParse({ ...assessment, criteria }).success,
    ).toBe(false);
  });
  it('does not accept a completed status without a result', () => {
    const completed = {
      requestId: '11111111-1111-4111-8111-111111111111',
      attempt: 1,
      status: 'succeeded',
      result: null,
    };
    expect(ApplicantCompletion.safeParse(completed).success).toBe(false);
    expect(
      ApplicantCompletion.safeParse({ ...completed, status: 'invalidated' })
        .success,
    ).toBe(true);
  });
});
