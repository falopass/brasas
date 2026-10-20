/* Pruebas de web/js/smoke.js con node:test, sin navegador ni dependencias.
 * fetch se simula en globalThis; cada test lo restaura. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { loadSmoke, SMOKE_COLOR, SMOKE_OPACITY } from '../../web/js/smoke.js';

let calls;
let responses;

const jsonRes = (status, body) => new Response(JSON.stringify(body), {
  status,
  headers: { 'content-type': 'application/json' },
});

const FC = {
  type: 'FeatureCollection',
  features: [{ type: 'Feature', geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] }, properties: { age_min: 12, cells: 40 } }],
};

// Las trampas van dentro del describe: los hooks a nivel de módulo corren para todas
// las suites del proceso (index.js las importa juntas) y pisarían el fetch de api.test.
describe('loadSmoke', () => {
  beforeEach(() => {
    calls = [];
    responses = [];
    globalThis.fetch = async (url) => {
      calls.push(url);
      const next = responses.shift();
      if (next instanceof Error) throw next;
      return next;
    };
  });

  afterEach(() => {
    delete globalThis.fetch;
  });

  test('pide solo la última hora y devuelve el FeatureCollection', async () => {
    responses.push(jsonRes(200, FC));
    const data = await loadSmoke();
    assert.equal(calls.length, 1);
    assert.equal(calls[0], '/api/opendata/smoke.geojson?hours=1');
    assert.equal(data.type, 'FeatureCollection');
    assert.equal(data.features.length, 1);
  });

  test('503 con detail del servidor → lanza ese mensaje', async () => {
    responses.push(jsonRes(503, { detail: 'El humo GOES-19 no está disponible ahora (GoesError). Intenta de nuevo en unos minutos.' }));
    const err = await loadSmoke().catch((e) => e);
    assert.ok(err instanceof Error);
    assert.match(err.message, /no está disponible ahora/);
  });

  test('200 sin FeatureCollection → error corto', async () => {
    responses.push(jsonRes(200, { detail: 'otra cosa' }));
    const err = await loadSmoke().catch((e) => e);
    assert.equal(err.message, 'El humo de GOES no está disponible ahora.');
  });

  test('sin conexión → el TypeError de fetch se propaga tal cual', async () => {
    responses.push(new TypeError('fetch failed'));
    const err = await loadSmoke().catch((e) => e);
    assert.ok(err instanceof TypeError);
  });
});

describe('paleta', () => {
  test('un gris por tema y opacidad baja', () => {
    assert.ok(SMOKE_COLOR.dark && SMOKE_COLOR.light);
    assert.ok(SMOKE_OPACITY > 0 && SMOKE_OPACITY <= 0.5);
  });
});
