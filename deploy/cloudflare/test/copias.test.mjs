// Pruebas de las copias públicas en R2 (OPS-817): con el contenedor dormido el borde
// sirve la copia que el cron dejó tras el último ciclo en vez de esperar el arranque
// en frío. Mismo patrón que cache.test.mjs: el backend y el bucket se inyectan.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cachedApi, EDGE_CACHE_TTL } from '../src/cache.ts';
import { claveCopia, COPIA_MAX_AGE_MS, esUrlCanonica, guardarCopias, META_GENERADA, URLS_CANONICAS } from '../src/copias.ts';

/* Respuesta con cabeceras inmutables, igual que las que devuelve fetch() (igual que
 * en cache.test.mjs): set/append/delete lanzan TypeError. */
function respuestaInmutable(body, init) {
  const r = new Response(body, init);
  const tira = () => { throw new TypeError('immutable'); };
  Object.assign(r.headers, { set: tira, append: tira, delete: tira });
  return r;
}

/* `objetos` es el contenido del bucket: clave R2 → {body, httpMetadata, customMetadata}. */
function montar(alBackend, objetos = new Map()) {
  const borde = new Map();
  globalThis.caches = {
    default: {
      match: async (key) => borde.get(key.url),
      put: async (key, res) => void borde.set(key.url, res),
    },
  };
  const ctx = { waitUntil: (p) => p.catch(() => {}) };
  const llamadas = [];
  const backend = async (req) => { llamadas.push(req.url); return alBackend(req); };
  const lecturas = [];
  const bucket = {
    get: async (key) => {
      lecturas.push(key);
      return objetos.get(key) || null;
    },
    put: async () => {},
  };
  return { ctx, backend, llamadas, bucket, lecturas, borde };
}

const get = (path) => new Request(`https://brasa.test${path}`);
const json200 = (data) => respuestaInmutable(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
const copiaJson = (data, generada) => ({
  body: JSON.stringify(data),
  httpMetadata: { contentType: 'application/json' },
  customMetadata: { [META_GENERADA]: String(generada) },
});

test('la lista canónica es la que la app pide al cargar', () => {
  assert.deepEqual(URLS_CANONICAS, [
    '/api/status',
    '/api/config',
    '/api/official-fires',
    '/api/risk',
    '/api/incidents?hours=48',
    '/api/observations?hours=24',
  ]);
});

test('esUrlCanonica compara path + consulta exactos', () => {
  const u = (p) => new URL(`https://brasa.test${p}`);
  for (const url of URLS_CANONICAS) assert.ok(esUrlCanonica(u(url)), `${url} debe ser canónica`);
  assert.ok(!esUrlCanonica(u('/api/risk?day=2026-11-09')), 'day no es canónico');
  assert.ok(!esUrlCanonica(u('/api/observations?hours=48')), 'otro hours no es canónico');
  assert.ok(!esUrlCanonica(u('/api/observations?hours=24&reliable=true')), 'un parámetro extra no es canónico');
  assert.ok(!esUrlCanonica(u('/api/incidents/abc123')), 'una ruta de incidente no es canónica');
  assert.ok(!esUrlCanonica(u('/api/places')), 'una ruta personal no es canónica');
  assert.ok(!esUrlCanonica(u('/api/status?history=20')), 'history no es canónico');
});

test('sin copia en el borde y con copia reciente en R2 se responde snapshot sin llamar al contenedor', async () => {
  const generada = Date.now() - 5 * 60_000;
  const objetos = new Map([[claveCopia('/api/official-fires'), copiaJson({ fires: [{ id: 1 }] }, generada)]]);
  const { ctx, backend, llamadas, bucket, lecturas, borde } = montar(() => json200({ fires: [] }), objetos);
  const res = await cachedApi(get('/api/official-fires'), ctx, EDGE_CACHE_TTL['/api/official-fires'], backend, bucket);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('X-Brasa-Cache'), 'snapshot');
  assert.deepEqual(lecturas, [claveCopia('/api/official-fires')]);
  assert.equal(llamadas.length, 0, 'la copia de R2 evita despertar al contenedor');
  assert.deepEqual(await res.json(), { fires: [{ id: 1 }] });
  assert.ok(borde.has('https://brasa.test/api/official-fires'), 'la copia queda guardada en el borde');
});

test('con copia vencida en el borde y copia reciente en R2 también se responde snapshot', async () => {
  const generada = Date.now() - 8 * 60_000;
  const objetos = new Map([[claveCopia('/api/risk'), copiaJson({ comunas: {} }, generada)]]);
  const { ctx, backend, llamadas, bucket, borde } = montar(() => json200({ comunas: { '13101': {} } }), objetos);
  // La copia del borde está vencida (x-brasa-fresh-until en el pasado).
  borde.set('https://brasa.test/api/risk', new Response('{"comunas":{}}', {
    headers: { 'x-brasa-fresh-until': '1', 'Cache-Control': 'public, max-age=600' },
  }));
  const res = await cachedApi(get('/api/risk'), ctx, EDGE_CACHE_TTL['/api/risk'], backend, bucket);
  assert.equal(res.headers.get('X-Brasa-Cache'), 'snapshot');
  assert.equal(llamadas.length, 0, 'la copia de R2 gana a la vencida sin llamar al contenedor');
});

test('con copia de más de 25 minutos se llama al contenedor como hoy', async () => {
  const generada = Date.now() - COPIA_MAX_AGE_MS - 60_000;
  const objetos = new Map([[claveCopia('/api/official-fires'), copiaJson({ fires: [{ id: 'vieja' }] }, generada)]]);
  const { ctx, backend, llamadas, bucket } = montar(() => json200({ fires: [{ id: 'del-contenedor' }] }), objetos);
  const res = await cachedApi(get('/api/official-fires'), ctx, EDGE_CACHE_TTL['/api/official-fires'], backend, bucket);
  assert.equal(res.headers.get('X-Brasa-Cache'), 'miss');
  assert.equal(llamadas.length, 1, 'copia vencida: se va al contenedor');
  assert.deepEqual(await res.json(), { fires: [{ id: 'del-contenedor' }] });
});

test('sin copia en R2 se llama al contenedor como hoy', async () => {
  const { ctx, backend, llamadas, bucket, lecturas } = montar(() => json200({ ok: true }));
  const res = await cachedApi(get('/api/status'), ctx, EDGE_CACHE_TTL['/api/status'], backend, bucket);
  assert.equal(res.headers.get('X-Brasa-Cache'), 'miss');
  assert.equal(llamadas.length, 1);
  assert.deepEqual(lecturas, [claveCopia('/api/status')], 'la URL canónica sí consulta R2 antes');
});

test('una URL no canónica nunca consulta R2', async () => {
  const { ctx, backend, llamadas, bucket, lecturas } = montar(() => json200({ points: [] }));
  const res = await cachedApi(get('/api/observations?hours=48'), ctx, EDGE_CACHE_TTL['/api/observations'], backend, bucket);
  assert.equal(res.headers.get('X-Brasa-Cache'), 'miss');
  assert.equal(lecturas.length, 0, 'hours=48 no es canónica: no se lee R2');
  assert.equal(llamadas.length, 1);
});

test('la copia de /api/status sale con la edad corregida desde su generación', async () => {
  const generada = Date.now() - 12 * 60_000; // la copia se generó hace 12 minutos
  const objetos = new Map([[claveCopia('/api/status'), copiaJson(
    { freshness: { age_seconds: 45, stale_after_s: 600, stale: false } }, generada,
  )]]);
  const { ctx, backend, llamadas, bucket } = montar(() => json200({}), objetos);
  const res = await cachedApi(get('/api/status'), ctx, EDGE_CACHE_TTL['/api/status'], backend, bucket);
  assert.equal(res.headers.get('X-Brasa-Cache'), 'snapshot');
  assert.equal(llamadas.length, 0);
  const data = await res.json();
  // 45 s declarados al generarse + ~720 s desde entonces, y stale se recalcula.
  assert.ok(data.freshness.age_seconds >= 45 + 720 - 3, `edad corregida (${data.freshness.age_seconds})`);
  assert.ok(data.freshness.age_seconds <= 45 + 720 + 3);
  assert.equal(data.freshness.stale, true);
});

test('guardarCopias escribe cada canónica bajo public/ con el instante de generación', async () => {
  const puts = [];
  const pedidos = [];
  const bucket = { put: async (key, value, options) => void puts.push({ key, value, options }) };
  const alBackend = async (req) => {
    pedidos.push(req);
    return new Response('{"ok":true}', { status: 200, headers: { 'content-type': 'application/json' } });
  };
  await guardarCopias(alBackend, bucket, 1700000000000);
  assert.equal(pedidos.length, URLS_CANONICAS.length);
  assert.equal(puts.length, URLS_CANONICAS.length);
  assert.equal(pedidos[0].headers.get('accept-encoding'), 'identity', 'las copias se piden sin compresión');
  assert.equal(puts[0].key, 'public/api/status');
  assert.equal(puts[0].options.customMetadata[META_GENERADA], '1700000000000');
  assert.equal(puts[0].options.httpMetadata.contentType, 'application/json');
  assert.equal(new TextDecoder().decode(puts[0].value), '{"ok":true}');
});

test('una copia que falla se registra y no interrumpe las demás', async () => {
  const puts = [];
  let n = 0;
  const alBackend = async () => (++n === 2 ? new Response('error', { status: 503 }) : new Response('{"ok":true}', { status: 200 }));
  const errores = [];
  const original = console.error;
  console.error = (...args) => errores.push(args);
  try {
    await guardarCopias(alBackend, { put: async (...a) => void puts.push(a) });
  } finally {
    console.error = original;
  }
  assert.equal(puts.length, URLS_CANONICAS.length - 1, 'la que no es 200 no se escribe');
  assert.equal(errores.length, 1, 'el fallo queda registrado');
});
