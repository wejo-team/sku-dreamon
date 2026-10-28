import { render, screen, within } from '@testing-library/react';
import { setupUser } from '@/test/user';
import { MemoryRouter, useLocation } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { ListPagination } from '@/components/common/ListPagination';

function renderPagination(page: number, totalPages: number) {
  const onNavigate = vi.fn();
  function Location() {
    const location = useLocation();
    return <output aria-label="현재 주소">{location.search}</output>;
  }
  render(
    <MemoryRouter initialEntries={[`/explore?tab=people&page=${page}`]}>
      <ListPagination
        page={page}
        totalPages={totalPages}
        hrefForPage={(nextPage) => `/explore?tab=people&page=${nextPage}`}
        onNavigate={onNavigate}
        label="사람 목록 페이지"
      />
      <Location />
    </MemoryRouter>,
  );
  return { onNavigate };
}

describe('ListPagination', () => {
  it('does not offer navigation for an empty collection', () => {
    renderPagination(1, 0);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });

  it('shows one current page and a disabled first-page control for one page', () => {
    const { onNavigate } = renderPagination(1, 1);
    const nav = screen.getByRole('navigation', { name: '사람 목록 페이지' });
    expect(within(nav).getByRole('link', { name: '1페이지' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(
      within(nav).getByRole('button', { name: '처음 페이지' }),
    ).toBeDisabled();
    expect(within(nav).getAllByRole('listitem')).toHaveLength(2);
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it.each([
    { page: 1, expectedPages: [1, 2, 3, 4, 5] },
    { page: 5, expectedPages: [3, 4, 5, 6, 7] },
    { page: 9, expectedPages: [5, 6, 7, 8, 9] },
  ])(
    'keeps a compact page window around page $page',
    ({ page, expectedPages }) => {
      renderPagination(page, 9);
      const nav = screen.getByRole('navigation', { name: '사람 목록 페이지' });
      const numberLinks = within(nav).getAllByRole('link', {
        name: /^\d+페이지$/,
      });
      expect(within(nav).getAllByRole('listitem')).toHaveLength(6);
      for (const name of ['이전 페이지', '다음 페이지', '마지막 페이지']) {
        expect(
          within(nav).queryByRole('link', { name }),
        ).not.toBeInTheDocument();
        expect(
          within(nav).queryByRole('button', { name }),
        ).not.toBeInTheDocument();
      }
      expect(numberLinks.map((link) => link.textContent)).toEqual(
        expectedPages.map(String),
      );
      expect(nav).toHaveAccessibleDescription(`전체 9페이지 중 ${page}페이지`);
      expect(
        within(nav).getByRole('link', { name: `${page}페이지` }),
      ).toHaveAttribute('aria-current', 'page');
    },
  );

  it('only offers existing page numbers for a short list', () => {
    renderPagination(2, 3);
    expect(
      screen
        .getAllByRole('link', { name: /^\d+페이지$/ })
        .map((link) => link.textContent),
    ).toEqual(['1', '2', '3']);
  });

  it.each([
    { label: '처음 페이지', target: 1 },
    { label: '6페이지', target: 6 },
  ])(
    'jumps directly with $label while retaining filters',
    async ({ label, target }) => {
      const { onNavigate } = renderPagination(4, 41);
      const user = setupUser();
      await user.click(screen.getByRole('link', { name: label }));
      expect(screen.getByLabelText('현재 주소')).toHaveTextContent(
        `?tab=people&page=${target}`,
      );
      expect(onNavigate).toHaveBeenCalledTimes(1);
    },
  );

  it('skips the disabled first-page control during keyboard navigation', async () => {
    renderPagination(1, 9);
    expect(screen.getByRole('button', { name: '처음 페이지' })).toBeDisabled();
    const user = setupUser();
    await user.tab();
    expect(screen.getByRole('link', { name: '1페이지' })).toHaveFocus();
  });

  it('supports keyboard activation in visible order and retains filters', async () => {
    const { onNavigate } = renderPagination(20, 41);
    const user = setupUser();
    await user.tab();
    expect(screen.getByRole('link', { name: '처음 페이지' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByLabelText('현재 주소')).toHaveTextContent(
      '?tab=people&page=1',
    );
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it('keeps valid backward page choices on the last page', () => {
    renderPagination(3, 3);
    expect(screen.getByRole('link', { name: '처음 페이지' })).toHaveAttribute(
      'href',
      '/explore?tab=people&page=1',
    );
    expect(screen.getByRole('link', { name: '2페이지' })).toHaveAttribute(
      'href',
      '/explore?tab=people&page=2',
    );
    expect(screen.getByRole('link', { name: '3페이지' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(
      screen.queryByRole('link', { name: '4페이지' }),
    ).not.toBeInTheDocument();
  });
});
