/* Teclado en el control «Capas» del mapa (MAPA-141). Una casilla deshabilitada mientras
 * carga su capa suelta el foco a <body> y el siguiente Tab se salta la capa: el recorrido
 * por teclado del E2E (scripts/local/browser_checks.py, check_mapa_teclado) lo comprobaba
 * en los tres anchos. La prueba viva es esa revisión en navegador; aquí queda la guarda
 * de que el control no vuelva a deshabilitar sus casillas. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const SRC = readFileSync(fileURLToPath(new URL('../../web/js/views/mapa.js', import.meta.url)), 'utf8');

describe('control de capas operable con teclado (MAPA-141)', () => {
  test('ninguna casilla del control se deshabilita: perdería el foco y Tab la saltaría', () => {
    assert.doesNotMatch(SRC, /\.disabled\s*=\s*true/, 'mapa.js deshabilita una casilla: el foco cae a <body> y Tab se salta la capa');
  });
  test('las capas de carga diferida siguen cargando al encenderse', () => {
    assert.match(SRC, /const lazy = \{ aire: loadSmoke, lightning: loadLightning \}\[key\]/);
    assert.match(SRC, /await lazy\(input\)/, 'setCapa debe esperar la carga diferida antes de pintar');
  });
});
