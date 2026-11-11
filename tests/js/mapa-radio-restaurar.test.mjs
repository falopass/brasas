/* VIS-03 corrección del 11-nov: decidirRestaurarRadio (web/js/views/mapa.js) decide
 * si el radio guardado se restaura al cargar sin mostrar un diálogo de permiso:
 * «ubicacion» solo con el permiso ya dado (getCurrentPosition no pregunta), «lugar»
 * con un primer lugar guardado, y null cuando no hay referencia sin diálogo —
 * queda «Todo Chile» y el guardado se conserva para cuando la persona toque un chip.
 * mapa.js se importa con un stub mínimo: solo lo usan el plegado de la leyenda y ui.js. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = { addEventListener() {} };
globalThis.document = { querySelector: () => null, getElementById: () => null, addEventListener() {}, dispatchEvent: () => true };
const { decidirRestaurarRadio } = await import('../../web/js/views/mapa.js');

describe('decidirRestaurarRadio (VIS-03)', () => {
  test('permiso dado restaura desde la ubicación, con o sin lugar guardado', () => {
    assert.equal(decidirRestaurarRadio(25, 'granted', false), 'ubicacion');
    assert.equal(decidirRestaurarRadio(100, 'granted', true), 'ubicacion');
  });

  test('sin permiso dado, un lugar guardado basta para restaurar', () => {
    assert.equal(decidirRestaurarRadio(25, 'prompt', true), 'lugar');
    assert.equal(decidirRestaurarRadio(25, 'denied', true), 'lugar');
    assert.equal(decidirRestaurarRadio(25, null, true), 'lugar'); // sin API de permisos
  });

  test('sin permiso ni lugar no se pide nada al cargar: queda «Todo Chile»', () => {
    assert.equal(decidirRestaurarRadio(25, 'prompt', false), null);
    assert.equal(decidirRestaurarRadio(25, 'denied', false), null);
    assert.equal(decidirRestaurarRadio(25, null, false), null);
  });

  test('radio no válido o «Todo Chile» (0) no restaura nada', () => {
    for (const km of [0, 7, -25, 'casa', null, undefined, NaN]) {
      assert.equal(decidirRestaurarRadio(km, 'granted', true), null, `km=${km}`);
    }
    for (const km of [10, 25, 50, 100]) {
      assert.notEqual(decidirRestaurarRadio(km, 'prompt', true), null, `km=${km}`);
    }
  });
});
