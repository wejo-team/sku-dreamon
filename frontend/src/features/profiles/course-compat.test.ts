// 구버전 서버가 과목 필드를 거절한 경우만 일반 입력 오류와 구분합니다.
import { describe, expect, it } from 'vitest';
import { isCourseFeatureUnavailable } from '@/features/profiles/api';
import { ApiError } from '@/lib/api';

const unsupportedCourseIssue = {
  loc: ['body', 'courseCodes'],
  msg: '입력값을 확인해 주세요.',
  type: 'extra_forbidden',
};

describe('course feature compatibility errors', () => {
  it('recognizes the legacy profile API rejection without relying on its message', () => {
    const error = new ApiError(422, {
      detail: [unsupportedCourseIssue],
    });
    expect(isCourseFeatureUnavailable(error)).toBe(true);
  });

  it.each([
    ['another field', { ...unsupportedCourseIssue, loc: ['body', 'realName'] }],
    ['invalid course data', { ...unsupportedCourseIssue, type: 'list_type' }],
    [
      'a nested course item',
      { ...unsupportedCourseIssue, loc: ['body', 'courseCodes', 0] },
    ],
    [
      'a nested object field',
      { ...unsupportedCourseIssue, loc: ['body', 'portfolio', 'courseCodes'] },
    ],
    [
      'a query parameter',
      { ...unsupportedCourseIssue, loc: ['query', 'courseCodes'] },
    ],
  ])('does not classify %s as a service version change', (_, issue) => {
    expect(
      isCourseFeatureUnavailable(new ApiError(422, { detail: [issue] })),
    ).toBe(false);
  });

  it('requires an HTTP validation failure', () => {
    expect(
      isCourseFeatureUnavailable(
        new ApiError(409, { detail: [unsupportedCourseIssue] }),
      ),
    ).toBe(false);
  });

  it.each([
    new ApiError(422, { detail: 'courseCodes extra_forbidden' }),
    new Error('courseCodes extra_forbidden'),
    null,
  ])(
    'does not classify an unstructured error as a service version change',
    (error) => {
      expect(isCourseFeatureUnavailable(error)).toBe(false);
    },
  );
});
