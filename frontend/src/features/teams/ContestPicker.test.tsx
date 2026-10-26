import { createRef, useState } from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ContestPicker } from '@/features/teams/ContestPicker';
import { createDemoRecords, type ContestSeed } from '@/features/demo/fixtures';
import { renderWithApi } from '@/test/render';

// 선택창은 GET /contests?registrationStatus=open&q=…(docs/api/contests.md#queries)로 목업 서버를 검색합니다.
// 서버 검색은 제목·주최자·분야 표시명 각각에 검색어 전체가 포함되는지 봅니다(대소문자 무시).
const records = createDemoRecords();
// 목업 기준 시각(2026-10-18)에 접수 중인 공모전을 바탕으로 식별자·제목·분야 코드만 바꿉니다.
const base = records.contests[0]!;
const uuid = (index: number) =>
  `00000000-0000-4000-8000-${index.toString(16).padStart(12, '0')}`;
// 목록 순서(등록 최신순)가 배열 순서와 같도록 등록 시각을 1분씩 앞당깁니다.
function contest(index: number, overrides: Partial<ContestSeed>): ContestSeed {
  return {
    ...base,
    id: uuid(index + 1),
    fieldCodes: ['education'],
    title: `공모전 ${index}`,
    organizer: '드림온 운영팀',
    description: '함께 도전하는 아이디어 공모전입니다.',
    createdAt: new Date(Date.UTC(2026, 8, 30) - index * 60_000)
      .toISOString()
      .replace('.000Z', 'Z'),
    ...overrides,
  };
}

const ids = { campus: uuid(1), craft: uuid(2), project: uuid(3) };
const fixtures = [
  contest(0, {
    title: 'Campus Idea Challenge',
    organizer: 'Dream On Lab',
  }),
  contest(1, {
    title: 'Local Craft Contest',
    organizer: '지역 문화 센터',
    fieldCodes: ['design'],
  }),
  contest(2, {
    title: 'Local Project Challenge',
    organizer: '지역 청년 재단',
    fieldCodes: ['it_technology'],
  }),
];

// 목업 저장소에 공모전을 둔 뒤 선택기를 그립니다.
async function renderPicker({
  contests = fixtures,
  initialValue = '',
  invalid = false,
}: {
  contests?: ContestSeed[];
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
  renderWithApi(<Form />, { db: { ...records, contests } });
  await screen.findByRole('button', { name: '참여 공모전' });
  return { onChange, onSubmit, onBlur, triggerRef };
}

async function openPicker(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: '참여 공모전' }));
  const drawer = await screen.findByRole('dialog', { name: '공모전 선택' });
  const search = within(drawer).getByRole('combobox', { name: '공모전 검색' });
  await waitFor(() => expect(search).toHaveFocus());
  return { drawer, search };
}

// 서버 응답을 받아 결과 수가 바뀔 때까지 기다립니다.
const expectOptions = (drawer: HTMLElement, count: number) =>
  waitFor(() =>
    expect(within(drawer).queryAllByRole('option')).toHaveLength(count),
  );

describe('ContestPicker', () => {
  it('connects the form label, error description and ref to its trigger and searches titles and organizers', async () => {
    const state = await renderPicker({ invalid: true });
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

    await user.type(search, '  CAMPUS idea  ');
    await expectOptions(drawer, 1);
    expect(within(drawer).getByRole('option')).toHaveTextContent(
      'Campus Idea Challenge',
    );
    await user.clear(search);
    await user.type(search, 'dream on');
    await waitFor(() =>
      expect(within(drawer).getByRole('option')).toHaveTextContent(
        'Dream On Lab',
      ),
    );
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '검색 결과 1개',
    );
    // 분야 표시명으로도 찾습니다.
    await user.clear(search);
    await user.type(search, '디자인');
    await waitFor(() =>
      expect(within(drawer).getByRole('option')).toHaveTextContent(
        'Local Craft Contest',
      ),
    );
    expect(state.onChange).not.toHaveBeenCalled();
    expect(state.onSubmit).not.toHaveBeenCalled();
  });

  it('shows an empty result and clears its search without changing the existing selection', async () => {
    const state = await renderPicker({ initialValue: ids.campus });
    const user = userEvent.setup();
    const { drawer, search } = await openPicker(user);
    await expectOptions(drawer, fixtures.length);
    await user.type(search, '없는 공모전 719');
    await waitFor(() =>
      expect(
        within(drawer).getByText('검색 결과가 없어요'),
      ).toBeInTheDocument(),
    );
    expect(within(drawer).queryAllByRole('option')).toHaveLength(0);
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
    await expectOptions(drawer, fixtures.length);
    expect(state.onChange).not.toHaveBeenCalled();
  });

  it.each(['닫기', 'Escape', 'outside'])(
    'keeps the chosen contest when dismissed with %s and clears the next search',
    async (dismissMethod) => {
      const state = await renderPicker({ initialValue: ids.campus });
      const user = userEvent.setup();
      const trigger = screen.getByRole('button', { name: '참여 공모전' });
      const { drawer, search } = await openPicker(user);
      await user.type(search, '지역 문화');
      await expectOptions(drawer, 1);
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
        ids.campus,
      );
      const reopened = await openPicker(user);
      expect(reopened.search).toHaveValue('');
      await expectOptions(reopened.drawer, fixtures.length);
      expect(
        within(reopened.drawer).getByRole('option', {
          name: /Campus Idea Challenge/,
        }),
      ).toHaveTextContent('현재 선택됨');
    },
  );

  it('distinguishes contests with the same title by their IDs and organizer metadata', async () => {
    const state = await renderPicker({
      initialValue: uuid(1),
      contests: [
        contest(0, { title: '같은 이름 공모전', organizer: '서울 센터' }),
        contest(1, { title: '같은 이름 공모전', organizer: '부산 센터' }),
      ],
    });
    const user = userEvent.setup();
    const { drawer } = await openPicker(user);
    await expectOptions(drawer, 2);
    await user.click(within(drawer).getByRole('option', { name: /부산 센터/ }));
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    expect(state.onChange).toHaveBeenCalledExactlyOnceWith(uuid(2));
    expect(screen.getByLabelText('선택한 공모전')).toHaveTextContent(uuid(2));
    expect(
      screen.getByRole('button', { name: '참여 공모전' }),
    ).toHaveTextContent('같은 이름 공모전');
    expect(
      screen.getByRole('button', { name: '참여 공모전' }),
    ).toHaveTextContent('부산 센터');
    expect(state.onSubmit).not.toHaveBeenCalled();
  });

  // Codex 리뷰 P2: 첫 페이지 밖의 공모전도 서버 더 보기·검색으로 찾을 수 있어야 합니다.
  it('limits a 125-contest list, expands it with the keyboard and searches the full collection on the server', async () => {
    const contests = Array.from({ length: 125 }, (_, index) =>
      contest(index, {
        title: `아이디어 공모전 ${String(index).padStart(3, '0')}`,
        organizer: index >= 120 ? '마지막 주최자' : '전국 창의 센터',
      }),
    );
    const state = await renderPicker({ contests });
    const user = userEvent.setup();
    const { drawer, search } = await openPicker(user);
    await expectOptions(drawer, 20);
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '검색 결과 125개 · 20개 표시',
    );
    within(drawer).getByRole('button', { name: '20개 더 보기' }).focus();
    await user.keyboard('{Enter}');
    await expectOptions(drawer, 40);
    expect(state.onChange).not.toHaveBeenCalled();
    expect(drawer).toBeInTheDocument();
    await user.type(search, '마지막 주최자');
    await expectOptions(drawer, 5);
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
    await expectOptions(drawer, 20);
    expect(state.onSubmit).not.toHaveBeenCalled();
  });

  it('respects IME composition and selects a keyboard-highlighted result without submitting the form', async () => {
    const state = await renderPicker();
    const user = userEvent.setup();
    const { drawer, search } = await openPicker(user);
    await user.type(search, 'local');
    await expectOptions(drawer, 2);
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
    expect(state.onChange).toHaveBeenCalledExactlyOnceWith(ids.project);
    expect(screen.getByLabelText('선택한 공모전')).toHaveTextContent(
      ids.project,
    );
  });
});
