/** 실제 항목 점수의 차트 비교·필터와 근거 미노출을 검증합니다. */
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ApplicantRecommendation } from '@/features/ai/contract';
import { renderWithApi } from '@/test/render';
import { setupUser } from '@/test/user';
import { ApplicantCandidateResults } from './ApplicantCandidateResults';
import { assessmentFixture } from './assessment-test-fixtures';

function candidate(index: number): ApplicantRecommendation {
  const assessment = assessmentFixture();
  if (index === 2)
    assessment.criteria[1] = {
      key: 'skills',
      score: null,
      informationStatus: 'insufficient',
      summary: '노출하지 않는 평가 설명',
      evidence: [],
    };
  return {
    applicationId: `00000000-0000-4000-8000-00000000000${index}`,
    title: `지원자 ${index}`,
    reason: '노출하지 않는 추천 이유',
    profileVersion: {
      accountId: `00000000-0000-4000-8000-00000000001${index}`,
      usedVersion: '1',
      currentVersion: '1',
    },
    profile: { skillCodes: index === 1 ? ['programming'] : ['ui_ux'] },
    assessment,
  };
}

describe('ApplicantCandidateResults', () => {
  it('compares actual scores on a bar chart without evidence, explanation panels, or tables', async () => {
    renderWithApi(
      <ApplicantCandidateResults candidates={[1, 2].map(candidate)} />,
    );
    const chart = await screen.findByRole('figure', {
      name: '지원자별 항목 점수 막대그래프',
    });
    expect(
      within(chart).getByText(
        '지원자 1: 역할 85점, 역량 75점, 경험 정보 부족으로 점수 없음, 참여 시간 정보 부족으로 점수 없음',
      ),
    ).toBeInTheDocument();
    expect(
      within(chart).getByText(
        '지원자 2: 역할 85점, 역량 정보 부족으로 점수 없음, 경험 정보 부족으로 점수 없음, 참여 시간 정보 부족으로 점수 없음',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    for (const text of [
      '노출하지 않는 추천 이유',
      '노출하지 않는 출처',
      '노출하지 않는 평가 설명',
      '기획자',
      '다른 활동을 포함한 시간인가요?',
    ])
      expect(screen.queryByText(text)).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '지원자 1 지원서 보기' }),
    ).toHaveAttribute(
      'href',
      '/applicants/00000000-0000-4000-8000-000000000001',
    );
  });
  it('lets the user change up to three chart series and recovers from an empty selection', async () => {
    renderWithApi(
      <ApplicantCandidateResults candidates={[1, 2, 3, 4].map(candidate)} />,
    );
    const user = setupUser();
    const fourth = await screen.findByRole('checkbox', {
      name: '지원자 4 비교에 포함',
    });
    expect(fourth).toBeDisabled();
    const legend = screen.getByLabelText('차트 범례');
    const secondColor = within(legend).getByText('지원자 2').className;
    const firstColor = within(legend).getByText('지원자 1').className;
    await user.click(
      screen.getByRole('checkbox', { name: '지원자 1 비교에 포함' }),
    );
    await user.click(fourth);
    expect(within(legend).getByText('지원자 2').className).toBe(secondColor);
    expect(within(legend).getByText('지원자 4').className).toBe(firstColor);
    const chart = screen.getByRole('figure', {
      name: '지원자별 항목 점수 막대그래프',
    });
    expect(within(chart).queryByText(/^지원자 1:/)).not.toBeInTheDocument();
    expect(within(chart).getByText(/^지원자 4:/)).toBeInTheDocument();
    for (const n of [2, 3, 4])
      await user.click(
        screen.getByRole('checkbox', { name: `지원자 ${n} 비교에 포함` }),
      );
    expect(screen.getByText('비교할 지원자를 선택해 주세요.')).toBeVisible();
    await user.click(
      screen.getByRole('checkbox', { name: '지원자 1 비교에 포함' }),
    );
    expect(
      screen.getByRole('figure', { name: '지원자별 항목 점수 막대그래프' }),
    ).toBeInTheDocument();
  });
  it('filters only current candidates and starts a fresh chart selection', async () => {
    renderWithApi(
      <ApplicantCandidateResults candidates={[1, 2].map(candidate)} />,
    );
    const user = setupUser();
    await user.click(await screen.findByText('역량 필터'));
    await user.selectOptions(
      screen.getByRole('combobox', { name: '등록 역량' }),
      'programming',
    );
    expect(screen.getByText('평가 2명 · 표시 1명')).toBeVisible();
    expect(
      screen.queryByRole('checkbox', { name: '지원자 2 비교에 포함' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('checkbox', { name: '지원자 1 비교에 포함' }),
    ).toBeChecked();
  });
});
