/* Pruebas de web/js/refresco.js: la edad del dato bajo el botón «Actualizar».
 * frescuraObs es pura: los casos corren sin DOM ni navegador. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

const { frescuraObs } = await import('../../web/js/refresco.js');

const NOW = Date.parse('2026-10-21T15:00:00Z');

describe('frescuraObs', () => {
  test('sin lote todavía', () => {
    assert.equal(frescuraObs({ status: null, dataAsOf: null, now: NOW }), 'Sin datos aún');
  });

  test('lote al día dice «Actualizado hace X»', () => {
    const status = { freshness: { stale: false, age_seconds: 120 } };
    assert.equal(frescuraObs({ status, dataAsOf: '2026-10-21T14:58:00Z', now: NOW }), 'Actualizado hace 2 min');
  });

  test('fuente atrasada dice «Sin datos nuevos hace X» con la edad de la peor', () => {
    const status = { freshness: { stale: true, products: {
      GOES: { stale: true, age_seconds: 5400 },
      FIRMS: { stale: false, age_seconds: 600 },
    } } };
    assert.equal(frescuraObs({ status, dataAsOf: '2026-10-21T13:30:00Z', now: NOW }), 'Sin datos nuevos hace 1 h');
  });

  test('una fuente caída con la marca global fresca también dice «sin datos nuevos»', () => {
    const status = { freshness: { stale: true, age_seconds: 120, products: {
      GOES: { stale: true, age_seconds: 7200 },
      FIRMS: { stale: false, age_seconds: 120 },
    } } };
    assert.equal(frescuraObs({ status, dataAsOf: '2026-10-21T14:58:00Z', now: NOW }), 'Sin datos nuevos hace 2 h');
  });

  test('sin bloque freshness aplica el respaldo de los 30 minutos', () => {
    assert.equal(frescuraObs({ status: null, dataAsOf: '2026-10-21T14:50:00Z', now: NOW }), 'Actualizado hace 10 min');
    assert.equal(frescuraObs({ status: null, dataAsOf: '2026-10-21T14:00:00Z', now: NOW }), 'Sin datos nuevos hace 1 h');
  });

  test('atrasado sin ninguna marca legible no inventa la edad', () => {
    const status = { freshness: { stale: true, products: { GOES: { stale: true, age_seconds: null } } } };
    assert.equal(frescuraObs({ status, dataAsOf: null, now: NOW }), 'Sin datos nuevos');
  });
});
