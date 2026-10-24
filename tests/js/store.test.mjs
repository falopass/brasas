/* Pruebas de web/js/store.js con node:test, sin navegador ni dependencias.
 * console.error se silencia guardando y restaurando la función. */
import { describe, test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { store } from '../../web/js/store.js';

const originalError = console.error;

afterEach(() => {
  console.error = originalError;
});

describe('store', () => {
  test('un manejador que lanza no impide notificar a los demás', () => {
    console.error = () => {};
    let recibido;
    store.on('view', () => {
      throw new Error('vista rota');
    });
    store.on('view', (v) => {
      recibido = v;
    });
    store.set('view', 'alertas');
    assert.equal(recibido, 'alertas');
  });

  test('set no propaga el error de un manejador', () => {
    console.error = () => {};
    store.on('status', () => {
      throw new Error('roto');
    });
    assert.doesNotThrow(() => store.set('status', { ok: true }));
    assert.deepEqual(store.get('status'), { ok: true });
  });

  test('on devuelve una función que deja de notificar', () => {
    console.error = () => {};
    let llamadas = 0;
    const off = store.on('risk', () => {
      llamadas += 1;
    });
    store.set('risk', 1);
    off();
    store.set('risk', 2);
    assert.equal(llamadas, 1);
    assert.equal(store.get('risk'), 2);
  });

  test('get devuelve lo último puesto y los defaults no cambian', () => {
    assert.equal(store.get('theme'), 'dark');
    assert.equal(store.get('obsHours'), 24);
    store.set('obsHours', 48);
    assert.equal(store.get('obsHours'), 48);
  });
});
