import { createRef, useState } from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ContestPicker } from './ContestPicker';
import type { Contest } from './data';

function contest(id: string, overrides: Partial<Contest> = {}): Contest {
  return {
    id,
    startsAt: '2026-10-01',
    officialUrl: 'https://example.org',
    participation: 'team',
    minMembers: 2,
    maxMembers: 5,
    status: 'open',
    deliverables: [],
    verifiedOn: '2026-10-18',
    interests: ['교육'],
    title: `공모전 ${id}`,
    organizer: '드림온 운영팀',
    category: '기획·아이디어',
    deadline: '2026.11.30',
    days: 30,
    audience: '대학생 누구나',
    description: '함께 도전하는 아이디어 공모전입니다.',
    teamCount: 2,
    ...overrides,
  };
}

const fixtures = [
  contest('campus', {
    title: 'Campus Idea Challenge',
    organizer: 'Dream On Lab',
  }),
  contest('craft', {
    title: 'Local Craft Contest',
    organizer: '지역 문화 센터',
    category: '디자인',
  }),
  contest('project', {
    title: 'Local Project Challenge',
    organizer: '지역 청년 재단',
    category: 'IT·기술',
  }),
];

function renderPicker({
  contests = fixtures,
  initialValue = '',
  invalid = false,
}: {
  contests?: readonly Contest[];
  initialValue?: string;
  invalid?: boolean;
} = {}) {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  const onBlur = vi.fn();
  const triggerRef = createRef<HTMLButtonElement>();
  function Form() {
    const [value, setValue] = useState(initialValue);
    return (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <label htmlFor="team-contest">참여 공모전</label>
        <ContestPicker
          ref={triggerRef}
          id="team-contest"
          contests={contests}
          value={value}
          onChange={(nextValue) => {
            onChange(nextValue);
            setValue(nextValue);
          }}
          invalid={invalid}
          describedBy="contest-help"
          onBlur={onBlur}
        />
        <p id="contest-help">참여할 공모전을 선택해 주세요.</p>
        <output aria-label="선택한 공모전">{value}</output>
        <button type="submit">팀 만들기</button>
      </form>
    );
  }
  render(<Form />);
  return { onChange, onSubmit, onBlur, triggerRef };
}

async function openPicker(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: '참여 공모전' }));
  const drawer = await screen.findByRole('dialog', { name: '공모전 선택' });
  const search = within(drawer).getByRole('combobox', { name: '공모전 검색' });
  await waitFor(() => expect(search).toHaveFocus());
  return { drawer, search };
}

describe('ContestPicker', () => {
  it('connects the form label, error description and ref to its trigger and searches titles and organizers', async () => {
    const state = renderPicker({ invalid: true });
    const user = userEvent.setup();
    const trigger = screen.getByRole('button', { name: '참여 공모전' });
    expect(state.triggerRef.current).toBe(trigger);
    expect(trigger).toHaveAttribute('aria-invalid', 'true');
    expect(trigger).toHaveAccessibleDescription(
      '참여할 공모전을 선택해 주세요.',
    );
    expect(trigger).toHaveTextContent('공모전 검색해서 선택');
    const { drawer, search } = await openPicker(user);
    expect(drawer).toHaveAccessibleDescription(
      '공모전 이름이나 주최자로 검색해 주세요.',
    );
    expect(state.onBlur).toHaveBeenCalled();

    await user.type(search, '  ＣＡＭＰＵＳ   idea  ');
    await waitFor(() =>
      expect(within(drawer).getAllByRole('option')).toHaveLength(1),
    );
    expect(within(drawer).getByRole('option')).toHaveTextContent(
      'Campus Idea Challenge',
    );
    await user.clear(search);
    await user.type(search, ' dream  ONlab ');
    expect(within(drawer).getAllByRole('option')).toHaveLength(1);
    expect(within(drawer).getByRole('option')).toHaveTextContent(
      'Dream On Lab',
    );
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '검색 결과 1개',
    );
    await user.clear(search);
    await user.type(search, 'campus dream');
    expect(within(drawer).getAllByRole('option')).toHaveLength(1);
    expect(within(drawer).getByRole('option')).toHaveTextContent(
      'Campus Idea Challenge',
    );
    expect(state.onChange).not.toHaveBeenCalled();
    expect(state.onSubmit).not.toHaveBeenCalled();
  });

  it('shows an empty result and clears its search without changing the existing selection', async () => {
    const state = renderPicker({ initialValue: 'campus' });
    const user = userEvent.setup();
    const { drawer, search } = await openPicker(user);
    await user.type(search, '없는 공모전 719');
    await waitFor(() =>
      expect(within(drawer).queryAllByRole('option')).toHaveLength(0),
    );
    expect(within(drawer).getByText('검색 결과가 없어요')).toBeInTheDocument();
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '검색 결과 0개',
    );
    await user.keyboard('{Enter}');
    expect(drawer).toBeInTheDocument();
    expect(state.onChange).not.toHaveBeenCalled();
    expect(state.onSubmit).not.toHaveBeenCalled();
    await user.click(
      within(drawer).getByRole('button', { name: '검색어 지우기' }),
    );
    expect(search).toHaveValue('');
    expect(search).toHaveFocus();
    expect(within(drawer).getAllByRole('option')).toHaveLength(fixtures.length);
    expect(state.onChange).not.toHaveBeenCalled();
  });

  it.each(['닫기', 'Escape', 'outside'])(
    'keeps the chosen contest when dismissed with %s and clears the next search',
    async (dismissMethod) => {
      const state = renderPicker({ initialValue: 'campus' });
      const user = userEvent.setup();
      const trigger = screen.getByRole('button', { name: '참여 공모전' });
      const { drawer, search } = await openPicker(user);
      await user.type(search, '지역 문화');
      expect(within(drawer).getAllByRole('option')).toHaveLength(1);
      if (dismissMethod === '닫기') {
        await user.click(within(drawer).getByRole('button', { name: '닫기' }));
      } else if (dismissMethod === 'Escape') {
        await user.keyboard('{Escape}');
      } else {
        const overlay = document.querySelector('[data-slot="drawer-overlay"]');
        expect(overlay).not.toBeNull();
        await user.click(overlay!);
      }
      await waitFor(() => expect(drawer).not.toBeInTheDocument());
      await waitFor(() => expect(trigger).toHaveFocus());
      expect(state.onChange).not.toHaveBeenCalled();
      expect(screen.getByLabelText('선택한 공모전')).toHaveTextContent(
        'campus',
      );
      const reopened = await openPicker(user);
      expect(reopened.search).toHaveValue('');
      expect(within(reopened.drawer).getAllByRole('option')).toHaveLength(
        fixtures.length,
      );
      expect(
        within(reopened.drawer).getByRole('option', {
          name: /Campus Idea Challenge/,
        }),
      ).toHaveTextContent('현재 선택됨');
    },
  );

  it('distinguishes contests with the same title by their IDs and organizer metadata', async () => {
    const state = renderPicker({
      initialValue: 'first',
      contests: [
        contest('first', { title: '같은 이름 공모전', organizer: '서울 센터' }),
        contest('second', {
          title: '같은 이름 공모전',
          organizer: '부산 센터',
        }),
      ],
    });
    const user = userEvent.setup();
    const { drawer } = await openPicker(user);
    expect(within(drawer).getAllByRole('option')).toHaveLength(2);
    await user.click(within(drawer).getByRole('option', { name: /부산 센터/ }));
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    expect(state.onChange).toHaveBeenCalledExactlyOnceWith('second');
    expect(screen.getByLabelText('선택한 공모전')).toHaveTextContent('second');
    expect(
      screen.getByRole('button', { name: '참여 공모전' }),
    ).toHaveTextContent('같은 이름 공모전');
    expect(
      screen.getByRole('button', { name: '참여 공모전' }),
    ).toHaveTextContent('부산 센터');
    expect(state.onSubmit).not.toHaveBeenCalled();
  });

  it('limits a 125-contest list, expands it with the keyboard and searches the full collection before limiting', async () => {
    const contests = Array.from({ length: 125 }, (_, index) =>
      contest(`contest-${index}`, {
        title: `아이디어 공모전 ${String(index).padStart(3, '0')}`,
        organizer: index >= 120 ? '마지막 주최자' : '전국 창의 센터',
      }),
    );
    const state = renderPicker({ contests });
    const user = userEvent.setup();
    const { drawer, search } = await openPicker(user);
    expect(within(drawer).getAllByRole('option')).toHaveLength(20);
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '검색 결과 125개 · 20개 표시',
    );
    within(drawer).getByRole('button', { name: '20개 더 보기' }).focus();
    await user.keyboard('{Enter}');
    expect(within(drawer).getAllByRole('option')).toHaveLength(40);
    expect(state.onChange).not.toHaveBeenCalled();
    expect(drawer).toBeInTheDocument();
    await user.type(search, '마지막주최자');
    expect(within(drawer).getAllByRole('option')).toHaveLength(5);
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '검색 결과 5개',
    );
    expect(
      within(drawer).getByRole('option', { name: /공모전 124/ }),
    ).toBeInTheDocument();
    expect(
      within(drawer).queryByRole('button', { name: /더 보기/ }),
    ).not.toBeInTheDocument();
    await user.clear(search);
    expect(within(drawer).getAllByRole('option')).toHaveLength(20);
    expect(state.onSubmit).not.toHaveBeenCalled();
  });

  it('respects IME composition and selects a keyboard-highlighted result without submitting the form', async () => {
    const state = renderPicker();
    const user = userEvent.setup();
    const { drawer, search } = await openPicker(user);
    await user.type(search, 'local');
    await waitFor(() =>
      expect(within(drawer).getAllByRole('option')).toHaveLength(2),
    );
    await waitFor(() =>
      expect(
        within(drawer).getByRole('option', { name: /Local Craft Contest/ }),
      ).toHaveAttribute('aria-selected', 'true'),
    );
    fireEvent.keyDown(search, {
      key: 'Enter',
      code: 'Enter',
      keyCode: 229,
      isComposing: true,
    });
    expect(state.onChange).not.toHaveBeenCalled();
    expect(drawer).toBeInTheDocument();
    await user.keyboard('{ArrowDown}{Enter}');
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    expect(state.onChange).toHaveBeenCalledExactlyOnceWith('project');
    expect(state.onSubmit).not.toHaveBeenCalled();
    expect(screen.getByLabelText('선택한 공모전')).toHaveTextContent('project');
  });
});
