// Pruebas de la caché del borde (OPS-34): una respuesta que no es 2xx llegaba al
// final de cachedApi con las cabeceras inmutables que entrega el fetch del binding,
// y `headers.set` lanzaba TypeError — Cloudflare respondía «error code: 1101» en vez
// del 422/503 real del contenedor.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cachedApi, EDGE_CACHE_TTL } from '../src/cache.ts';

/* Respuesta con cabeceras inmutables, igual que las que devuelve fetch() (y el binding
 * del contenedor): set/append/delete lanzan TypeError. En Node no hay API pública para
 * la guardia «immutable», así que se parchean los métodos de Headers. */
function respuestaInmutable(body, init) {
  const r = new Response(body, init);
  const tira = () => { throw new TypeError('immutable'); };
  Object.assign(r.headers, { set: tira, append: tira, delete: tira });
  return r;
}

function montar(alBackend) {
  const copias = new Map();
  globalThis.caches = {
    default: {
      match: async (key) => copias.get(key.url),
      put: async (key, res) => void copias.set(key.url, res),
    },
  };
  const ctx = { waitUntil: (p) => p.catch(() => {}) };
  const llamadas = [];
  const backend = async (req) => { llamadas.push(req.url); return alBackend(req); };
  return { ctx, backend, llamadas };
}

const get = (path) => new Request(`https://brasa.test${path}`);

test('un 422 del contenedor llega al cliente con su código real (OPS-34)', async () => {
  const { ctx, backend } = montar(async () =>
    respuestaInmutable(JSON.stringify({ detail: 'hours debe ser >= 1' }), {
      status: 422,
      headers: { 'Content-Type': 'application/json' },
    }));
  const res = await cachedApi(get('/api/observations?hours=0'), ctx, EDGE_CACHE_TTL['/api/observations'], backend);
  assert.equal(res.status, 422);
  assert.equal(res.headers.get('X-Brasa-Cache'), 'pass');
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
  assert.deepEqual(await res.json(), { detail: 'hours debe ser >= 1' });
});

test('el 503 «iniciando» del arranque en frío pasa con su Retry-After', async () => {
  const { ctx, backend } = montar(async () =>
    respuestaInmutable(JSON.stringify({ detail: 'iniciando' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json', 'Retry-After': '5' },
    }));
  const res = await cachedApi(get('/api/status'), ctx, EDGE_CACHE_TTL['/api/status'], backend);
  assert.equal(res.status, 503);
  assert.equal(res.headers.get('Retry-After'), '5');
  assert.equal(res.headers.get('X-Brasa-Cache'), 'pass');
});

test('un 200 se guarda en el borde y la segunda visita es hit', async () => {
  const { ctx, backend, llamadas } = montar(async () =>
    respuestaInmutable('{"ok":true}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
  const res1 = await cachedApi(get('/api/status'), ctx, EDGE_CACHE_TTL['/api/status'], backend);
  assert.equal(res1.status, 200);
  assert.equal(res1.headers.get('X-Brasa-Cache'), 'miss');
  const res2 = await cachedApi(get('/api/status'), ctx, EDGE_CACHE_TTL['/api/status'], backend);
  assert.equal(res2.headers.get('X-Brasa-Cache'), 'hit');
  assert.equal(llamadas.length, 1, 'la segunda visita no vuelve al contenedor');
});
