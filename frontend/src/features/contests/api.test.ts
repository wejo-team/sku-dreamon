// 실제 공고 상세 전송 형태와 미확인 출처를 읽는 클라이언트 계약을 검증합니다.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getContest } from '@/features/contests/api';
import { createDemoRecords, deriveContest } from '@/features/demo/fixtures';

afterEach(() => vi.unstubAllGlobals());

const db = createDemoRecords();
const seed = deriveContest(db.contests[0]!, db);
const detail = {
  ...seed,
  officialUrl: 'https://organizer.example.com/contest',
  timing: { ...seed.timing, openTimeDefaulted: true },
};

function respond(data: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ data })));
}

describe('contest detail source contract', () => {
  it.each([
    ['confirmed official notice', detail.verifiedAt, detail.officialUrl],
    ['unverified organizer link', null, detail.officialUrl],
    ['unverified collected source', null, null],
  ])(
    'reads %s without inventing verification',
    async (_, verifiedAt, officialUrl) => {
      const response = { ...detail, verifiedAt, officialUrl };
      respond(response);
      await expect(getContest(detail.id)).resolves.toEqual(response);
    },
  );

  it.each(['officialUrl', 'openTimeDefaulted'])(
    'rejects an omitted %s instead of treating it as verified data',
    async (key) => {
      const response = structuredClone(detail);
      if (key === 'officialUrl') Reflect.deleteProperty(response, key);
      else Reflect.deleteProperty(response.timing, key);
      respond(response);
      await expect(getContest(detail.id)).rejects.toThrow();
    },
  );

  it('keeps strict response validation for unexpected source metadata', async () => {
    respond({ ...detail, sourceMetadata: { provider: 'internal' } });
    await expect(getContest(detail.id)).rejects.toThrow();
  });

  it.each([400, 404])(
    'preserves HTTP %s errors before parsing the success contract',
    async (status) => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          Response.json(
            {
              error: {
                code: 'CONTEST_NOT_FOUND',
                message: '공고를 확인할 수 없습니다.',
              },
              requestId: 'contest-contract-error',
            },
            { status },
          ),
        ),
      );
      await expect(getContest(detail.id)).rejects.toMatchObject({
        status,
        requestId: 'contest-contract-error',
      });
    },
  );
});
