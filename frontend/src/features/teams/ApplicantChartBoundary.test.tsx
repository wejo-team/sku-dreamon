/** 차트 로딩 실패가 주변 지원서 이동까지 중단시키지 않는지 검증합니다. */
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ApplicantChartBoundary } from './ApplicantChartBoundary';

it('contains a chart failure and keeps the surrounding application link available', () => {
  const report = vi.spyOn(console, 'error').mockImplementation(() => {});
  function BrokenChart(): never {
    throw new Error('Failed to fetch dynamically imported module');
  }
  try {
    render(
      <>
        <ApplicantChartBoundary>
          <BrokenChart />
        </ApplicantChartBoundary>
        <a href="/applicants/example">지원서 보기</a>
      </>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(
      '차트를 불러오지 못했어요.',
    );
    expect(screen.getByRole('button', { name: '화면 새로고침' })).toBeEnabled();
    expect(screen.getByRole('link', { name: '지원서 보기' })).toBeVisible();
  } finally {
    report.mockRestore();
  }
});
