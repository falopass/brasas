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
  test('casos y riesgo usan el bloque compartido y no traen copia local', () => {
    for (const vista of ['web/js/views/casos.js', 'web/js/views/riesgo.js']) {
      const src = leer(vista);
      assert.ok(!src.includes('function loadError'), `${vista} aún define loadError`);
      assert.ok(src.includes("from '../errores.js'"), `${vista} no importa errores.js`);
      assert.ok(src.includes('errorConSalida('), `${vista} no llama a errorConSalida`);
    }
  });
});
