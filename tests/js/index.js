/* Punto de entrada para `node --test tests/js/`: Node trata los argumentos de --test como globs
 * y «tests/js» coincide con el propio directorio, que se ejecuta como script; sin este index.js
 * falla con MODULE_NOT_FOUND. Las suites *.test.mjs se descubren solas, en orden alfabético:
 * basta con crear tests/js/<tema>.test.mjs. */
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

/* web/js/speak.js resuelve `window.speechSynthesis` al importarse y varias vistas lo
 * arrastran (views/zona.js, vecino.js): su suite, que instala el speechSynthesis falso,
 * se importa primero para que esa resolución no quede en null según el orden alfabético. */
const PRIMERO = 'speak.test.mjs';

const dir = dirname(fileURLToPath(import.meta.url));
const suites = readdirSync(dir).filter((n) => n.endsWith('.test.mjs')).sort();
for (const name of [...suites.filter((n) => n === PRIMERO), ...suites.filter((n) => n !== PRIMERO)]) {
  await import(pathToFileURL(join(dir, name)).href);
}
