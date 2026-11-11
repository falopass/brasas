/* Buscador del mapa operable con teclado (VIS-01). La medición en producción
 * (Playwright, 11-nov-2026) mostró que escribir «talca», bajar con la flecha y
 * apretar Enter no elegía nada, y que el teclado del teléfono autocorregía y
 * ponía mayúsculas. La prueba viva del recorrido es la revisión en navegador;
 * aquí quedan las guardas de que bindBuscarComuna conserva sus atajos y el
 * input los atributos que apagan la autocorrección. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const SRC = readFileSync(fileURLToPath(new URL('../../web/js/views/mapa.js', import.meta.url)), 'utf8');
const BLOQUE = SRC.slice(SRC.indexOf('function bindBuscarComuna'));
const INPUT = SRC.match(/<input[^>]*id="map-search"[^>]*>/)?.[0] ?? '';

describe('buscador del mapa con teclado (VIS-01)', () => {
  test('Enter con resultados elige el primero', () => {
    assert.match(BLOQUE, /key === 'Enter' && hits\.length[\s\S]{0,120}elegir\(0\)/);
  });
  test('Flecha abajo baja al primer resultado', () => {
    assert.match(BLOQUE, /key === 'ArrowDown'[\s\S]{0,200}querySelector\('\.search-hit'\)[\s\S]{0,120}\.focus\(\)/);
  });
  test('las flechas recorren la lista y Flecha arriba vuelve al campo', () => {
    assert.match(BLOQUE, /results\.addEventListener\('keydown'/);
    assert.match(BLOQUE, /key === 'ArrowUp'[\s\S]{0,160}\|\| search\)\.focus\(\)/);
  });
  test('Escape cierra la lista', () => {
    assert.match(BLOQUE, /key === 'Escape'/);
  });
  test('el campo anuncia su lista con aria-expanded y aria-controls', () => {
    assert.match(INPUT, /role="combobox"/);
    assert.match(INPUT, /aria-controls="map-search-results"/);
    assert.match(BLOQUE, /aria-expanded/);
  });
  test('el teclado del teléfono no autocorrige ni pone mayúsculas', () => {
    for (const attr of ['autocapitalize="off"', 'autocorrect="off"', 'spellcheck="false"', 'inputmode="search"', 'autocomplete="off"']) {
      assert.match(INPUT, new RegExp(attr), `#map-search sin ${attr}`);
    }
  });
});
