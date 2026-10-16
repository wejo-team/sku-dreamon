import { afterEach, describe, expect, expectTypeOf, it, vi } from 'vitest';
import { z } from 'zod';
import { getHealth, healthSchema, type HealthResponse } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('health API contract', () => {
  it('keeps the runtime schema output equal to the generated response type', () => {
    expectTypeOf<
      z.output<typeof healthSchema>
    >().toEqualTypeOf<HealthResponse>();
  });

  it('accepts the response and ignores additional fields', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(Response.json({ status: 'ok', extra: 'future' })),
    );
    await expect(getHealth()).resolves.toEqual({ status: 'ok' });
  });

  it.each([{}, { status: 'degraded' }, { status: null }, { status: 1 }])(
    'rejects invalid response %j before it reaches query state',
    async (body) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));
      await expect(getHealth()).rejects.toBeInstanceOf(z.ZodError);
    },
  );
});
