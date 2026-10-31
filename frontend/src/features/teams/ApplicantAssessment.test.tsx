/** 실제 점수와 누락값의 시각적 구분 및 근거 미노출을 검증합니다. */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ApplicantAssessment } from './ApplicantAssessment';
import { assessmentFixture } from './assessment-test-fixtures';

describe('ApplicantAssessment', () => {
  it('shows four scores or patterned empty tracks without evidence or questions', () => {
    const assessment = assessmentFixture();
    render(<ApplicantAssessment assessment={assessment} />);
    const chart = screen.getByRole('figure', { name: '항목별 평가 점수' });
    for (const label of ['역할', '역량', '경험', '참여 시간'])
      expect(within(chart).getByText(label)).toBeVisible();
    expect(screen.getByRole('img', { name: '역할: 85점' })).toHaveAttribute(
      'data-score',
      '85',
    );
    expect(screen.getByRole('img', { name: '역량: 75점' })).toHaveAttribute(
      'data-score',
      '75',
    );
    const missing = screen.getByRole('img', {
      name: '경험: 정보 부족으로 점수 없음',
    });
    expect(missing).not.toHaveAttribute('data-score');
    expect(missing.querySelector('rect')).toHaveAttribute(
      'stroke-dasharray',
      '3 4',
    );
    expect(within(missing).getByText('—')).toBeInTheDocument();
    for (const criterion of assessment.criteria) {
      expect(screen.queryByText(criterion.summary)).not.toBeInTheDocument();
      for (const evidence of criterion.evidence)
        expect(screen.queryByText(evidence.text)).not.toBeInTheDocument();
    }
    expect(
      screen.queryByText(assessment.questions[0]!),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/정보 부족|확인 불가|확인됨/),
    ).not.toBeInTheDocument();
  });

  it('distinguishes an evaluated zero from missing data when scores change', () => {
    const assessment = assessmentFixture();
    const view = render(<ApplicantAssessment assessment={assessment} />);
    view.rerender(
      <ApplicantAssessment
        assessment={{
          ...assessment,
          criteria: assessment.criteria.map((criterion) =>
            criterion.key === 'role'
              ? { ...criterion, score: 0, informationStatus: 'sufficient' }
              : {
                  ...criterion,
                  score: null,
                  informationStatus: 'insufficient',
                },
          ),
        }}
      />,
    );
    const zero = screen.getByRole('img', { name: '역할: 0점' });
    expect(within(zero).getByText('0')).toBeInTheDocument();
    expect(zero.querySelector('[stroke-dasharray]')).toBeNull();
    expect(
      screen.getAllByRole('img', { name: /정보 부족으로 점수 없음/ }),
    ).toHaveLength(3);
    expect(screen.getAllByText('—')).toHaveLength(3);
  });
});
