// @vitest-environment node
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, it } from 'vitest';
import { syncApiTypes } from './api-contract.mjs';

it('generates reproducible types and detects missing or stale output without changing it', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'wejo-api-types-test-'));
  const outputPath = join(directory, 'schema.d.ts');
  try {
    await expect(syncApiTypes({ outputPath, check: true })).rejects.toThrow(
      'missing or stale',
    );
    await expect(readFile(outputPath)).rejects.toMatchObject({
      code: 'ENOENT',
    });
    await syncApiTypes({ outputPath });
    const first = await readFile(outputPath, 'utf8');
    await syncApiTypes({ outputPath });
    expect(await readFile(outputPath, 'utf8')).toBe(first);
    await expect(
      syncApiTypes({ outputPath, check: true }),
    ).resolves.toBeUndefined();

    await writeFile(outputPath, '// stale generated contract\n');
    await expect(syncApiTypes({ outputPath, check: true })).rejects.toThrow(
      'missing or stale',
    );
    expect(await readFile(outputPath, 'utf8')).toBe(
      '// stale generated contract\n',
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}, 20_000);
