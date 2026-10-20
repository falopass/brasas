/* Pruebas de las funciones puras de web/js/views/alertas.js con node:test (UX-50):
 * kindLabel traduce el `kind` del aviso al motivo que lee la persona; sin `kind`
 * conocido devuelve '' y la vista no muestra etiqueta: nunca se inventa un motivo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { kindLabel } from '../../web/js/views/alertas.js';

describe('kindLabel', () => {
  test('traduce cada motivo conocido', () => {
    assert.equal(kindLabel('oficial'), 'CONAF informa');
    assert.equal(kindLabel('reporte'), 'Un vecino reportó');
    assert.equal(kindLabel('diario'), 'Prevención del día');
    assert.equal(kindLabel('prueba'), 'Prueba');
  });
  test('un kind desconocido no inventa un motivo', () => {
    assert.equal(kindLabel('dmc'), '');
    assert.equal(kindLabel(''), '');
  });
  test('sin kind no hay etiqueta', () => {
    assert.equal(kindLabel(undefined), '');
    assert.equal(kindLabel(null), '');
  });
});
