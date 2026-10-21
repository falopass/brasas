/* Pruebas de firmsQuota, openMeteoQuota y ultimosErrores en web/js/views/calidad.js con
 * node:test (DAT-01, CALIDAD-02): los bloques de cupo deciden entre «sin dato», la lectura con
 * porcentaje y el aviso del 80 %, y la línea de errores traduce las claves del último ciclo.
 * calidad.js importa ui.js, que registra un listener «online» al cargar: se usa un stub. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = { addEventListener() {} };
const { firmsQuota, openMeteoQuota, ultimosErrores } = await import('../../web/js/views/calidad.js');

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

const meteo = (over = {}) => ({
  since: '2026-10-20T00:00:00Z', calls: 40, locations: 670, by_endpoint: {},
  by_endpoint_locations: {}, rate_limited: 0, daily_cap: 1000, scheduled: 400, ...over,
});

describe('openMeteoQuota', () => {
  test('con cifras muestra usado de tope, el porcentaje y nombra la prioridad', () => {
    const t = String(openMeteoQuota({ open_meteo: meteo() }));
    assert.match(t, /670 de 1\.000 ubicaciones hoy \(67 %\)/);
    assert.match(t, /pronóstico( &gt;| >) FWI/);
    assert.match(t, /normales( &gt;| >) casos/);
    assert.doesNotMatch(t, /callout-warn/);
  });
  test('al 80 % o más del tope avisa qué se degrada primero', () => {
    const t = String(openMeteoQuota({ open_meteo: meteo({ locations: 900 }) }));
    assert.match(t, /\(90 %\)/);
    assert.match(t, /callout-warn/);
    assert.match(t, /casos históricos/);
  });
  test('sin datos dice sin dato con el motivo, nunca un cero inventado', () => {
    const t = String(openMeteoQuota({}));
    assert.match(t, /Sin dato del cupo/);
    assert.match(t, /aún no publica/);
    assert.doesNotMatch(t, /ubicaciones hoy/);
  });
  test('con el contador del proceso en cero usa el acumulado durable del día', () => {
    const t = String(openMeteoQuota({ open_meteo: meteo({ locations: 10, scheduled: { total: 500 } }) }));
    assert.match(t, /500 de 1\.000 ubicaciones hoy \(50 %\)/);
  });
});

describe('ultimosErrores', () => {
  test('traduce las claves al nombre de la fuente y qué mirar', () => {
    const t = String(ultimosErrores({ errors: { cycle_errors: ['firms_error'] } }));
    assert.match(t, /FIRMS/);
    assert.match(t, /qué mirar/);
    assert.doesNotMatch(t, /firms_error/);
  });
  test('sin errores dice que la ronda quedó limpia', () => {
    const t = String(ultimosErrores({ errors: { cycle_errors: [] } }));
    assert.match(t, /sin errores/);
  });
  test('con error en el resumen o sin bloque dice sin detalle, sin romper', () => {
    const t = String(ultimosErrores({ errors: { error: true } }));
    assert.match(t, /sin detalle/i);
    const sinBloque = String(ultimosErrores({}));
    assert.match(sinBloque, /sin detalle/i);
  });
});
