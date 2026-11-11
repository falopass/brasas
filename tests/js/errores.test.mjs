/* Pruebas del bloque de error compartido (web/js/errores.js, ERRORES-01): mismo marcado
 * en todas las vistas, mensaje escapado y «Reintentar» enlazado, sin navegador.
 * errores.js importa ui.js, que registra un listener «online» al cargar: se usa un stub. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

globalThis.window ??= { addEventListener() {} };
const { errorConSalida, errorConSalidaHtml } = await import('../../web/js/errores.js');

const leer = (rel) => readFileSync(fileURLToPath(new URL(`../../${rel}`, import.meta.url)), 'utf8');

describe('errorConSalidaHtml', () => {
  test('escapa el mensaje de error', () => {
    const salida = errorConSalidaHtml(new Error('<b>rompí</b>'));
    assert.ok(!salida.includes('<b>rompí</b>'));
    assert.ok(salida.includes('&lt;b&gt;rompí&lt;/b&gt;'));
  });
  test('trae la alerta, el reintento y los teléfonos de emergencia', () => {
    const salida = errorConSalidaHtml(new Error('sin señal'));
    for (const parte of ['role="alert"', 'data-retry', 'tel:130', 'tel:132']) {
      assert.ok(salida.includes(parte), `falta ${parte}`);
    }
  });
  test('con mensaje propio nombra lo que falló y deja el detalle en la lectura técnica', () => {
    const salida = errorConSalidaHtml(new Error('boom'), 'No se pudo cargar este incendio histórico.');
    assert.ok(salida.includes('No se pudo cargar este incendio histórico.'));
    assert.ok(salida.includes('Error al cargar: boom'));
    assert.ok(salida.includes('data-retry'));
    assert.ok(salida.includes('tel:132'));
  });
});

describe('errorConSalida', () => {
  test('un clic en [data-retry] invoca retry exactamente una vez', () => {
    let llamadas = 0;
    let handler = null;
    const boton = { addEventListener: (evento, fn) => { assert.equal(evento, 'click'); handler = fn; } };
    const host = { innerHTML: '', querySelector: (sel) => { assert.equal(sel, '[data-retry]'); return boton; } };
    errorConSalida(host, new Error('x'), () => { llamadas += 1; });
    assert.ok(host.innerHTML.includes('data-retry'));
    handler(); // un clic
    assert.equal(llamadas, 1);
  });
  test('casos usa el bloque compartido y no trae copia local', () => {
    const src = leer('web/js/views/casos.js');
    assert.ok(!src.includes('function loadError'), 'casos.js aún define loadError');
    assert.ok(src.includes("from '../errores.js'"), 'casos.js no importa errores.js');
    assert.ok(src.includes('errorConSalida('), 'casos.js no llama a errorConSalida');
  });
  /* VIS-02: el error de riesgo nombra la consulta que falló, así que el bloque es
   * propio (errores.js no se pudo tocar en este encargo); lo que se conserva es el
   * marcado del compartido: alerta, «Reintentar» y teléfonos de emergencia. */
  test('riesgo mantiene alerta, reintento y teléfonos en su error nombrado', () => {
    const src = leer('web/js/views/riesgo.js');
    assert.ok(!src.includes('function loadError'), 'riesgo.js aún define loadError');
    for (const parte of ['role="alert"', 'data-retry', 'phonesHtml()', 'Reintentar']) {
      assert.ok(src.includes(parte), `riesgo.js sin ${parte}`);
    }
    assert.ok(src.includes('No pudimos cargar el peligro de incendio por comuna.'), 'la vista no nombra la consulta que falló');
  });
});
