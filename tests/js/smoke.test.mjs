/* Pruebas de web/js/smoke.js con node:test, sin navegador ni dependencias. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { loadSmoke, SMOKE_COLORS } from '../../web/js/smoke.js';

let calls;
let responses;

const jsonRes = (status, body, type = 'application/geo+json') => new Response(JSON.stringify(body), {
  status,
  headers: { 'content-type': type },
});

describe('loadSmoke', () => {
  beforeEach(() => {
    calls = [];
    responses = [];
    globalThis.fetch = async (url, init) => {
      calls.push({ url, init });
      const next = responses.shift();
      if (next instanceof Error) throw next;
      return next;
    };
  });

  afterEach(() => {
    delete globalThis.fetch;
  });

  test('devuelve un FeatureCollection con solo type y features', async () => {
    const feature = { type: 'Feature', geometry: { type: 'Polygon', coordinates: [] }, properties: { cells: 3 } };
    responses.push(jsonRes(200, { type: 'FeatureCollection', source: 'NOAA GOES-19', hours: 1, features: [feature] }));
    const data = await loadSmoke();
    assert.deepEqual(data, { type: 'FeatureCollection', features: [feature] });
    assert.equal(calls[0].url, '/api/opendata/smoke.geojson?hours=1');
  });

  test('un no-200 lanza un error corto', async () => {
    responses.push(new Response('boom', { status: 503 }));
    const err = await loadSmoke().catch((e) => e);
    assert.equal(err.message, 'El humo de GOES no está disponible ahora');
  });

  test('sin conexión lanza el mismo error corto', async () => {
    responses.push(new TypeError('fetch failed'));
    const err = await loadSmoke().catch((e) => e);
    assert.equal(err.message, 'El humo de GOES no está disponible ahora');
  });

  test('una respuesta 200 sin forma de colección lanza error corto', async () => {
    responses.push(jsonRes(200, { type: 'FeatureCollection', features: null }));
    const err = await loadSmoke().catch((e) => e);
    assert.equal(err.message, 'Respuesta de humo inválida.');
  });

  test('la paleta tiene un gris para cada tema', () => {
    assert.ok(SMOKE_COLORS.dark && SMOKE_COLORS.light);
  });
});
