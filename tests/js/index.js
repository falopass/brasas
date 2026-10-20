/* Punto de entrada para `node --test tests/js/`: Node trata los argumentos de --test como globs
 * y «tests/js» coincide con el propio directorio, que se ejecuta como script; sin este index.js
 * falla con MODULE_NOT_FOUND. Descubre e importa solo las suites *.test.mjs, en orden
 * alfabético: agregar una prueba es crear el archivo, sin tocar este índice.
 * Una suite que revienta al cargar se reporta como prueba fallida y no silencia a las demás. */
import { test } from 'node:test';
import { readdirSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const dir = dirname(fileURLToPath(import.meta.url));
const suites = readdirSync(dir)
  .filter((name) => name.endsWith('.test.mjs'))
  .sort();

for (const name of suites) {
  try {
    await import(pathToFileURL(join(dir, name)).href);
  } catch (err) {
    test(`carga de ${name}`, () => { throw err; });
  }
}
