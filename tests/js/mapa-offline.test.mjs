/* Pruebas de web/js/mapa-offline.js (MAPA-166): la matemática de teselas es pura y
 * el descargador se prueba con fetch y Cache API de mentira, sin red ni navegador. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  bboxLugar, descargarMapa, GLYPH_RANGOS, metaMapa, PARALELO, recursosDescarga,
  tesela, teselasLugar, TILEJSON_URL, Z_MAX, Z_MIN,
} from '../../web/js/mapa-offline.js';

const LUGAR = { id: 'p1', name: 'Casa', lat: -33.0, lon: -71.41, radius_km: 2 };
const PLANTILLA = 'https://tiles.openfreemap.org/planet/v1/{z}/{x}/{y}.pbf';

/* localStorage de mentira para la meta (patrón de inventario.test.mjs). */
const mem = new Map();
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
};

const cacheFake = () => {
  const m = new Map();
  return {
    _map: m,
    match: async (url) => m.get(typeof url === 'string' ? url : url.url),
    keys: async () => [...m.keys()].map((url) => ({ url })),
    put: async (url, res) => { m.set(typeof url === 'string' ? url : url.url, res); },
    matchAll: async () => [...m.values()],
  };
};

const respOk = (bytes, tipo = 'application/x-protobuf') => ({
  ok: true,
  headers: { get: () => tipo },
  arrayBuffer: async () => new Uint8Array(bytes).buffer,
});
const respTilejson = () => ({
  ok: true,
  headers: { get: () => 'application/json' },
  arrayBuffer: async () => new TextEncoder().encode(JSON.stringify({ tiles: [PLANTILLA] })).buffer,
});
const fetchFake = (handler) => {
  const calls = [];
  const fn = async (url) => { calls.push(url); return handler(url); };
  return { fn, calls };
};

describe('tesela (slippy map)', () => {
  test('el origen y el ecuador caen donde deben', () => {
    assert.deepEqual(tesela(0, 0, 0), [0, 0]);
    assert.deepEqual(tesela(-180, 85.0511, 1), [0, 0]);
    assert.deepEqual(tesela(0, 0, 1), [1, 1]);
    assert.deepEqual(tesela(179.9, -85.0511, 1), [1, 1]);
  });

  test('un punto de Chile conocido cae en su tesela', () => {
    // Quilpué (-71.41, -33.0) a zoom 13: valores calculados con la fórmula slippy map.
    const [x, y] = tesela(-71.41, -33.0, 13);
    const n = 2 ** 13;
    assert.ok(x === Math.floor(((-71.41 + 180) / 360) * n));
    assert.ok(y > 0 && y < n);
  });
});

describe('bboxLugar y teselasLugar', () => {
  test('la caja es simétrica alrededor del lugar y crece con el radio', () => {
    const [w, s, e, n] = bboxLugar(LUGAR);
    assert.ok(Math.abs((w + e) / 2 - LUGAR.lon) < 1e-9);
    assert.ok(Math.abs((s + n) / 2 - LUGAR.lat) < 1e-9);
    const grande = bboxLugar({ ...LUGAR, radius_km: 10 });
    assert.ok(grande[0] < w && grande[2] > e);
  });

  test('cubre el centro en todos los zooms 8–13, sin duplicados', () => {
    const lista = teselasLugar(LUGAR);
    const claves = new Set(lista.map((t) => `${t.z}/${t.x}/${t.y}`));
    assert.equal(claves.size, lista.length);
    for (let z = Z_MIN; z <= Z_MAX; z++) {
      const [cx, cy] = tesela(LUGAR.lon, LUGAR.lat, z);
      assert.ok(lista.some((t) => t.z === z && t.x === cx && t.y === cy), `falta la tesela central en z${z}`);
    }
    assert.ok(Math.min(...lista.map((t) => t.z)) === Z_MIN && Math.max(...lista.map((t) => t.z)) === Z_MAX);
  });

  test('un lugar más grande pide más teselas', () => {
    assert.ok(teselasLugar({ ...LUGAR, radius_km: 20 }).length > teselasLugar(LUGAR).length);
  });
});

describe('recursosDescarga', () => {
  test('va primero un glyph por rango y después las teselas con la plantilla', () => {
    const urls = recursosDescarga(LUGAR, PLANTILLA);
    const nTiles = teselasLugar(LUGAR).length;
    assert.equal(urls.length, GLYPH_RANGOS.length + nTiles);
    assert.ok(urls[0].endsWith('0-255.pbf'));
    assert.ok(urls.slice(0, GLYPH_RANGOS.length).every((u) => u.includes('/fonts/Noto%20Sans%20Regular/')));
    assert.ok(urls[GLYPH_RANGOS.length].match(/\/planet\/v1\/\d+\/\d+\/\d+\.pbf$/));
  });
});

describe('descargarMapa', () => {
  test('descarga completa: guarda todo y deja la meta del lugar', async () => {
    const { fn } = fetchFake((url) => (url === TILEJSON_URL ? respTilejson() : respOk(100)));
    const cache = cacheFake();
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache, ahora: () => '2026-10-26T12:00:00Z' });
    const total = recursosDescarga(LUGAR, PLANTILLA).length;
    assert.equal(r.completo, true);
    assert.equal(r.recursos, total);
    assert.equal(r.bytes, total * 100);
    assert.equal(cache._map.size, total + 1); // + el TileJSON
    const meta = metaMapa()[LUGAR.id];
    assert.equal(meta.completo, true);
    assert.equal(meta.at, '2026-10-26T12:00:00Z');
  });

  test('respeta el tope de bytes y lo declara incompleto', async () => {
    const { fn } = fetchFake((url) => (url === TILEJSON_URL ? respTilejson() : respOk(100)));
    const cache = cacheFake();
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache, topeBytes: 350 });
    assert.equal(r.completo, false);
    assert.equal(r.motivo, 'tope');
    assert.ok(r.bytes <= 350 + PARALELO * 100); // las peticiones en vuelo terminan
    assert.ok(r.recursos < r.total);
  });

  test('en error de red corta tras un solo reintento y guarda lo que haya', async () => {
    const { fn, calls } = fetchFake((url) => {
      if (url === TILEJSON_URL) return respTilejson();
      throw new Error('sin red');
    });
    const cache = cacheFake();
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache });
    assert.equal(r.completo, false);
    assert.equal(r.motivo, 'red');
    assert.equal(cache._map.size, 1); // solo el TileJSON
    // Un reintento por recurso en cada uno de los PARALELO workers, y nada más.
    assert.equal(calls.filter((u) => u !== TILEJSON_URL).length, PARALELO * 2);
  });

  test('un 404 salta el recurso sin cortar la descarga', async () => {
    const { fn } = fetchFake((url) => {
      if (url === TILEJSON_URL) return respTilejson();
      if (url.includes('/fonts/')) return { ok: false, status: 404, headers: { get: () => null } };
      return respOk(10);
    });
    const cache = cacheFake();
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache });
    assert.equal(r.completo, true);
    assert.equal(r.recursos, r.total); // los 404 cuentan como revisados, no como bajados
    assert.ok(r.bytes < r.total * 10);
  });

  test('lo ya guardado en la caché no se vuelve a bajar ni a cobrar', async () => {
    const cache = cacheFake();
    const urls = recursosDescarga(LUGAR, PLANTILLA);
    await cache.put(urls[0], respOk(999));
    await cache.put(urls[1], respOk(999));
    const { fn, calls } = fetchFake((url) => (url === TILEJSON_URL ? respTilejson() : respOk(10)));
    const r = await descargarMapa(LUGAR, { fetchImpl: fn, cache });
    assert.equal(r.completo, true);
    assert.equal(r.recursos, r.total);
    assert.ok(!calls.includes(urls[0]) && !calls.includes(urls[1]));
    assert.equal(r.bytes, (r.total - 2) * 10);
  });
});

