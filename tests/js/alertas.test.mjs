/* Pruebas de kindLabel de web/js/views/alertas.js (UX-50): el historial dice por qué
 * llegó cada aviso, y un origen desconocido no muestra etiqueta (no se inventa un motivo). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = {};
const { kindLabel } = await import('../../web/js/views/alertas.js');

describe('kindLabel', () => {
  test('cada origen conocido tiene su etiqueta', () => {
    assert.equal(kindLabel('oficial'), 'CONAF informa');
    assert.equal(kindLabel('reporte'), 'Un vecino reportó');
    assert.equal(kindLabel('diario'), 'Prevención del día');
    assert.equal(kindLabel('prueba'), 'Prueba');
  });
  test('un origen desconocido no muestra etiqueta', () => {
    assert.equal(kindLabel('satelite'), '');
    assert.equal(kindLabel(undefined), '');
  });
});
