/* Punto de entrada para `node --test tests/js/`: Node trata los argumentos de --test como globs
 * y «tests/js» coincide con el propio directorio, que se ejecuta como script; sin este index.js
 * falla con MODULE_NOT_FOUND. Descubre e importa solo las suites *.test.mjs del directorio,
 * en orden alfabético: agregar una prueba es crear el archivo, sin tocar este índice. */
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const dir = fileURLToPath(new URL('.', import.meta.url));
const suites = readdirSync(dir).filter((name) => name.endsWith('.test.mjs')).sort();
for (const name of suites) {
  await import(pathToFileURL(join(dir, name)).href);
}
