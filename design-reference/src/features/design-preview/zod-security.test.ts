// 독립 lockfile의 Zod가 제한 초과 배열의 요소 검증을 시작하지 않는지 확인한다.
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';

describe('Zod bounded collection protection', () => {
  it('rejects an oversized array before parsing invalid elements', () => {
    // 디자인 참고 앱도 별도 의존성에서 배열 검증의 과도한 연산을 막아야 한다.
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
