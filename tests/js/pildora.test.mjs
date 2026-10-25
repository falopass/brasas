/* Pruebas de web/js/pildora.js (PILDORA-01): la píldora distingue «sin señal en el
 * teléfono», «el servidor de BRASA no responde» y «los datos están viejos». Módulo
 * puro: los casos del criterio de listo corren sin DOM ni navegador. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

const { pillState, debeRefrescar } = await import('../../web/js/pildora.js');

const NOW = Date.parse('2026-10-21T15:00:00Z');
const err500 = { status: 500, code: undefined, message: 'El servidor no pudo completar la solicitud.' };
const err503 = { status: 503, code: undefined, message: 'El servidor no pudo completar la solicitud.' };
const statusFresco = {
  last_ingest_at: '2026-10-21T14:58:00Z',
  freshness: { stale: false, age_seconds: 120 },
  newest_observation: { abi: '2026-10-21T14:55:00Z' },
};
const statusViejo = {
  last_ingest_at: '2026-10-21T13:30:00Z',
  freshness: { stale: true, age_seconds: 5400 },
  newest_observation: { abi: '2026-10-21T13:20:00Z' },
};

describe('pillState', () => {
  test('un 500 con buena señal culpa a BRASA, no a la conexión', () => {
    const p = pillState({ online: true, statusError: err500, status: null, cachedAt: null, now: NOW });
    assert.equal(p.state, 'servidor');
    assert.equal(p.text, 'BRASA no responde · reintentando');
    assert.ok(!p.text.includes('Sin conexión'));
  });

  test('sin señal en el teléfono sigue diciendo «Sin conexión»', () => {
    const p = pillState({ online: false, statusError: null, status: null, cachedAt: null, now: NOW });
    assert.equal(p.state, 'offline');
    assert.equal(p.text, 'Sin conexión');
    assert.equal(p.short, 'Sin conexión');
  });

  test('la solicitud que no sale (OFFLINE/TIMEOUT) también es «Sin conexión»', () => {
    for (const code of ['OFFLINE', 'TIMEOUT']) {
      const p = pillState({ online: true, statusError: { status: 0, code }, status: null, cachedAt: null, now: NOW });
      assert.equal(p.state, 'offline', code);
    }
  });

  test('un 503 tres veces seguidas queda en «servidor» sin parpadear', () => {
    const lecturas = [0, 1, 2].map(() => pillState({ online: true, statusError: err503, status: null, cachedAt: null, now: NOW }));
    assert.deepEqual(lecturas.map((p) => p.state), ['servidor', 'servidor', 'servidor']);
    assert.deepEqual([...new Set(lecturas.map((p) => p.text))], ['BRASA no responde · reintentando']);
  });

  test('datos viejos con servidor sano mantienen el texto de siempre', () => {
    const p = pillState({ online: true, statusError: null, status: statusViejo, cachedAt: null, now: NOW });
    assert.equal(p.state, 'stale');
    assert.equal(p.text, 'Datos de hace 90 min');
    assert.equal(p.short, 'Hace 90 min');
    assert.ok(p.title.startsWith('Los datos satelitales están atrasados'));
  });

  test('una respuesta buena tras un fallo vuelve a «live»', () => {
    const caido = pillState({ online: true, statusError: err500, status: null, cachedAt: null, now: NOW });
    assert.equal(caido.state, 'servidor');
    const p = pillState({ online: true, statusError: null, status: statusFresco, cachedAt: null, now: NOW });
    assert.equal(p.state, 'live');
    assert.equal(p.text, 'Actualizado hace 2 min');
    assert.equal(p.short, 'Hace 2 min');
  });

  test('el estado guardado por el service worker informa la edad del dato', () => {
    const p = pillState({ online: true, statusError: null, status: statusFresco, cachedAt: '2026-10-21T14:30:00Z', now: NOW });
    assert.equal(p.state, 'offline');
    assert.equal(p.text, 'Sin conexión · datos de hace 30 min');
  });

  test('sin respuesta ni estado todavía: «sin-datos»', () => {
    const p = pillState({ online: true, statusError: null, status: null, cachedAt: null, now: NOW });
    assert.equal(p.state, 'sin-datos');
    assert.equal(p.text, 'Esperando los primeros datos');
  });
});

/* MZ-06: cuándo Mi zona vuelve a pedir el resumen de sus lugares — vista visible,
 * al menos 60 s desde el último resumen, y lote nuevo de focos o vuelta >2 min. */
describe('debeRefrescar (MZ-06)', () => {
  const base = { ultimo: NOW - 5 * 60000, ahora: NOW, visible: true };

  test('con la vista oculta nunca refresca, ni por lote nuevo ni por volver', () => {
    assert.equal(debeRefrescar({ ...base, visible: false, motivo: 'focos' }), false);
    assert.equal(debeRefrescar({ ...base, visible: false, motivo: 'volver' }), false);
  });

  test('menos de 60 s desde el último resumen no refresca por ningún motivo', () => {
    assert.equal(debeRefrescar({ ultimo: NOW - 30 * 1000, ahora: NOW, visible: true, motivo: 'focos' }), false);
    assert.equal(debeRefrescar({ ultimo: NOW - 59 * 1000, ahora: NOW, visible: true, motivo: 'volver' }), false);
  });

  test('un lote nuevo de focos refresca pasados los 60 s', () => {
    assert.equal(debeRefrescar({ ...base, motivo: 'focos' }), true);
    assert.equal(debeRefrescar({ ultimo: NOW - 60 * 1000, ahora: NOW, visible: true, motivo: 'focos' }), true);
  });

  test('volver antes de 2 min no refresca', () => {
    assert.equal(debeRefrescar({ ultimo: NOW - 90 * 1000, ahora: NOW, visible: true, motivo: 'volver' }), false);
    assert.equal(debeRefrescar({ ultimo: NOW - 120 * 1000, ahora: NOW, visible: true, motivo: 'volver' }), false);
  });

  test('volver después de 2 min sí refresca', () => {
    assert.equal(debeRefrescar({ ultimo: NOW - 121 * 1000, ahora: NOW, visible: true, motivo: 'volver' }), true);
    assert.equal(debeRefrescar({ ...base, motivo: 'volver' }), true);
  });

  test('cualquier otro motivo no refresca', () => {
    assert.equal(debeRefrescar({ ...base, motivo: 'manual' }), false);
    assert.equal(debeRefrescar({ ...base }), false);
  });

  test('acepta la hora del último resumen como ISO o como ms', () => {
    const iso = new Date(NOW - 5 * 60000).toISOString();
    assert.equal(debeRefrescar({ ultimo: iso, ahora: NOW, visible: true, motivo: 'focos' }), true);
    assert.equal(debeRefrescar({ ultimo: null, ahora: NOW, visible: true, motivo: 'focos' }), true);
  });
});
