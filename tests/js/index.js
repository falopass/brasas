/* Punto de entrada para `node --test tests/js/`: Node trata los argumentos de --test como globs
 * y «tests/js» coincide con el propio directorio, que se ejecuta como script; sin este index.js
 * falla con MODULE_NOT_FOUND. Las suites *.test.mjs se descubren solas, en orden alfabético:
 * basta con crear tests/js/<tema>.test.mjs. */
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const dir = dirname(fileURLToPath(import.meta.url));
for (const name of readdirSync(dir).filter((n) => n.endsWith('.test.mjs')).sort()) {
  await import(pathToFileURL(join(dir, name)).href);
}
