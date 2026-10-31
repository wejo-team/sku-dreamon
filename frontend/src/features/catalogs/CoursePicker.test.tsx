// 검색과 페이지가 바뀌어도 선택을 보존하고 API 실패에서 복구하는 과목 선택 흐름을 검증합니다.

import { useState } from 'react';
import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CoursePicker } from '@/features/catalogs/CoursePicker';
import type { CourseSummary } from '@/features/catalogs/api';
import { createDemoRecords } from '@/features/demo/fixtures';
import { renderWithApi, settled } from '@/test/render';
import { fill, setupUser } from '@/test/user';

function Picker() {
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  return <CoursePicker value={courses} onChange={setCourses} />;
}

const records = () => ({
  ...createDemoRecords(),
  courses: Array.from({ length: 21 }, (_, index) => ({
    code: `CS${String(index).padStart(4, '0')}`,
    name: `교과목 ${index}`,
    aliases: index === 20 ? ['이전과목명'] : [],
    departments: ['소프트웨어학과'],
  })),
});

describe('course selection', () => {
  it('keeps selections across server searches and pages, without duplicate codes', async () => {
    const { client } = renderWithApi(<Picker />, { db: records() });
    await settled(client);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const user = setupUser();
    await user.click(
      screen.getByRole('checkbox', { name: '교과목 0 (CS0000)' }),
    );
    await user.click(screen.getByRole('button', { name: '다음 과목 페이지' }));
    await user.click(
      await screen.findByRole('checkbox', { name: '교과목 20 (CS0020)' }),
    );
    expect(screen.getByText('선택한 과목 2개')).toBeInTheDocument();
    const search = screen.getByRole('searchbox', {
      name: '과목명 또는 학수번호',
    });
    await fill(user, search, 'CS0000');
    expect(
      await screen.findByRole('checkbox', { name: '교과목 0 (CS0000)' }),
    ).toBeChecked();
    expect(screen.getByText('선택한 과목 2개')).toBeInTheDocument();
    await user.clear(search);
    await fill(user, search, '이전과목명');
    expect(
      await screen.findByRole('checkbox', { name: '교과목 20 (CS0020)' }),
    ).toBeChecked();
    const requestedUrls = fetchSpy.mock.calls.map(([url]) => String(url));
    expect(
      requestedUrls.some(
        (url) =>
          new URL(url, 'http://test.invalid').searchParams.get('q') ===
          '이전과목명',
      ),
    ).toBe(true);
    await user.click(
      screen.getByRole('button', { name: '교과목 0 (CS0000) 선택 해제' }),
    );
    expect(
      within(screen.getByRole('list', { name: '선택한 수강과목' })).queryByText(
        '교과목 0',
      ),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: '교과목 20 (CS0020) 선택 해제' }),
    );
    expect(screen.getByText('선택한 과목 0개')).toBeInTheDocument();
  });

  it('keeps selection visible when search has no results', async () => {
    const { client } = renderWithApi(<Picker />, { db: records() });
    await settled(client);
    const user = setupUser();
    await user.click(
      screen.getByRole('checkbox', { name: '교과목 0 (CS0000)' }),
    );
    await fill(user, screen.getByRole('searchbox'), '없는과목');
    expect(
      await screen.findByText(
        '검색 결과가 없어요. 다른 과목명이나 학수번호로 검색해 주세요.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '교과목 0 (CS0000) 선택 해제' }),
    ).toBeInTheDocument();
  });

  it('retries a failed course request without blocking the optional field', async () => {
    let fail = true;
    renderWithApi(<Picker />, {
      db: records(),
      fail: (request) => request.path === '/catalogs/courses' && fail,
    });
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '과목을 불러오지 못했어요.',
    );
    fail = false;
    await setupUser().click(
      screen.getByRole('button', { name: '과목 다시 불러오기' }),
    );
    await waitFor(() =>
      expect(screen.getAllByRole('checkbox')).toHaveLength(20),
    );
  });
});
