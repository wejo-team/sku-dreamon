/** 실제 0점과 자료 부족을 구분하고 긴 근거를 표시하지 않는지 확인합니다. */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ApplicantAssessment } from './ApplicantAssessment';
import { createApplicantAssessment } from './applicant-assessment';
import { initialApplicants, profileToPerson } from './data';

describe('지원자 점수 차트 레퍼런스', () => {
  it('renders a real zero score and an unscored item differently', () => {
    const applicant = initialApplicants[0]!;
    const assessment = createApplicantAssessment(applicant, {
      ...profileToPerson(applicant.profile!),
      experienceState: 'unspecified',
      experience: '',
    });
    assessment.criteria[0]!.score = 0;
    render(<ApplicantAssessment assessment={assessment} />);
    expect(screen.getByRole('img', { name: '역할: 0점' })).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: '경험: 자료 부족으로 점수 없음' }),
    ).toBeInTheDocument();
    expect(screen.getByText('0')).toBeVisible();
    expect(screen.getAllByText('—')).toHaveLength(2);
    expect(screen.queryByText('정보 부족')).not.toBeInTheDocument();
    expect(
      screen.queryByText(assessment.criteria[0]!.summary),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(assessment.questions[0]!),
    ).not.toBeInTheDocument();
  });
});
