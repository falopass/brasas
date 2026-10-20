/* Pruebas de firmsQuota en web/js/views/calidad.js con node:test (DAT-01): el bloque del cupo
 * de la clave FIRMS decide entre «sin dato», la lectura con porcentaje y el aviso del 80 %.
 * calidad.js importa ui.js, que registra un listener «online» al cargar: se usa un stub. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = { addEventListener() {} };
const { firmsQuota } = await import('../../web/js/views/calidad.js');

const quota = (over = {}) => ({ limit: 5000, used: 1200, checked_at: '2026-10-20T12:00:00Z', error: false, ...over });
const status = (q = quota()) => ({ firms_configured: true, firms_quota: q });

describe('firmsQuota', () => {
  test('con cifras muestra usado de límite, el porcentaje y la hora', () => {
    const t = String(firmsQuota(status()));
    assert.match(t, /1\.200 de 5\.000 transacciones en la ventana de 10 minutos/);
    assert.match(t, /\(24 %\)/);
    assert.match(t, /consultado (hace|recién)/);
    assert.doesNotMatch(t, /callout-warn/);
  });
  test('al 80 % o más del límite avisa del 429', () => {
    const t = String(firmsQuota(status(quota({ used: 4600 }))));
    assert.match(t, /\(92 %\)/);
    assert.match(t, /callout-warn/);
    assert.match(t, /429/);
  });
  test('sin clave configurada dice sin dato y por qué', () => {
    const t = String(firmsQuota({ firms_configured: false, firms_quota: null }));
    assert.match(t, /Sin dato del cupo/);
    assert.match(t, /no tiene clave/);
  });
  test('con error o sin cifras dice sin dato, sin inventar números', () => {
    const conError = String(firmsQuota(status(quota({ error: true }))));
    assert.match(conError, /Sin dato del cupo/);
    assert.doesNotMatch(conError, /transacciones en la ventana/);
    const sinLectura = String(firmsQuota(status({ limit: null, used: null, checked_at: null, error: false })));
    assert.match(sinLectura, /Sin dato del cupo/);
  });
});
