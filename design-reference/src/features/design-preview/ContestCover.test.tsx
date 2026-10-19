import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ContestCover } from './ContestCover';

describe('contest cover fallback', () => {
  it('uses the mascot when the poster is missing or blank', () => {
    const { container, rerender } = render(<ContestCover />);
    const cover = container.querySelector('img')!;
    expect(cover).toHaveAttribute('src', '/contest-covers/skon-default.png');
    rerender(<ContestCover src="   " />);
    expect(cover).toHaveAttribute('src', '/contest-covers/skon-default.png');
  });

  it('replaces a failed poster and tries a newly supplied image', () => {
    const { container, rerender } = render(<ContestCover src="/poster.png" />);
    const cover = container.querySelector('img')!;
    expect(cover).toHaveAttribute('src', '/poster.png');
    fireEvent.error(cover);
    expect(cover).toHaveAttribute('src', '/contest-covers/skon-default.png');
    rerender(<ContestCover src="/updated-poster.png" />);
    expect(cover).toHaveAttribute('src', '/updated-poster.png');
  });
});
