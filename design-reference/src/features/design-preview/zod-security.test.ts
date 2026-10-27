import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';

describe('Zod bounded collection protection', () => {
  it('rejects an oversized array before parsing invalid elements', () => {
    // This app has its own lockfile: keep the bounded-array DoS fix covered here.
    const readFirst = vi.fn(() => null);
    const values = Array<unknown>(1_000).fill(null);
    Object.defineProperty(values, 0, { get: readFirst });

    const result = z.array(z.string()).max(3).safeParse(values);

    expect(result.success).toBe(false);
    expect(readFirst).not.toHaveBeenCalled();
    if (!result.success) {
      expect(result.error.issues).toEqual([
        expect.objectContaining({ code: 'too_big', maximum: 3 }),
      ]);
    }
  });
});
