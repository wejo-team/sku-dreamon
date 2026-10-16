import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createClient } from '@hey-api/openapi-ts';
import { format, resolveConfig } from 'prettier';

const frontendRoot = fileURLToPath(new URL('../', import.meta.url));
const snapshot = resolve(frontendRoot, '../contracts/openapi.json');
const generated = resolve(frontendRoot, 'src/lib/api-schema.generated.d.ts');

export async function syncApiTypes({
  outputPath = generated,
  check = false,
} = {}) {
  const temporary = await mkdtemp(join(tmpdir(), 'wejo-api-types-'));
  try {
    await createClient({
      input: snapshot,
      output: temporary,
      plugins: ['@hey-api/typescript'],
      logs: { level: 'silent', file: false },
    });
    const source = await readFile(join(temporary, 'types.gen.ts'), 'utf8');
    const content = await format(source, {
      ...(await resolveConfig(generated)),
      parser: 'typescript',
    });

    if (check) {
      let existing;
      try {
        existing = await readFile(outputPath, 'utf8');
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
      if (existing !== content) {
        throw new Error(
          'API types are missing or stale. Run `npm run api:generate`.',
        );
      }
      return;
    }
    await writeFile(outputPath, content, 'utf8');
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

if (resolve(process.argv[1] ?? '') === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length > 1 || (args.length === 1 && args[0] !== '--check')) {
    console.error('Usage: node scripts/api-contract.mjs [--check]');
    process.exitCode = 1;
  } else {
    try {
      await syncApiTypes({ check: args.includes('--check') });
      console.log(
        args.includes('--check')
          ? 'API types are current.'
          : 'Generated API types.',
      );
    } catch (error) {
      console.error(error.message);
      process.exitCode = 1;
    }
  }
}
