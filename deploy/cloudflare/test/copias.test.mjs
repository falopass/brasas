/** Copia pública en R2 (OPS-817): el borde sirve las URL canónicas desde la copia del
 *  último ciclo antes de despertar al contenedor. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cachedApi } from '../src/cache.ts';
import { URLS_CANONICAS, esUrlCanonica, claveCopia, guardarCopias, META_GENERADA } from '../src/copias.ts';

const ORIGEN = 'https://x';
const u = (path) => new URL(path, ORIGEN);
const req = (url) => new Request(url, { method: 'GET' });
const resp = (cuerpo, headers = {}) => new Response(JSON.stringify(cuerpo), {
  status: 200,
  headers: { 'content-type': 'application/json', ...headers },
});
const ctxFalso = () => ({ waitUntil() {} });

// La caché del borde, igual que en cache.test.mjs: se reemplaza el global por prueba.
function conCache(entries = new Map()) {
  globalThis.caches = {
    default: {
      match: async (key) => entries.get(key.url)?.clone(),
      put: async (key, res) => void entries.set(key.url, res.clone()),
    },
  };
  return entries;
}

// Entrada del borde como la escribe edgeFill: frescura relativa a su llenado y sello
// `x-brasa-generada` con el instante en que se produjo el dato.
function entrada(freshIn_s, generadaIn_s = freshIn_s - 1) {
  return resp({ ok: true }, {
    'x-brasa-fresh-until': String(Math.floor(Date.now() / 1000) + freshIn_s),
    'x-brasa-generada': String(Math.floor(Date.now() / 1000) + generadaIn_s),
  });
}

// Objeto R2 como lo deja guardarCopias: el cuerpo de la respuesta y `generada` en metadata.
const copia = (generadaHace_s, cuerpo = { ok: true }) => ({
  body: new TextEncoder().encode(JSON.stringify(cuerpo)),
  httpMetadata: { contentType: 'application/json' },
  customMetadata: { [META_GENERADA]: String(Date.now() - generadaHace_s * 1000) },
});
const copiaBucket = (objeto) => ({ async get() { return objeto; } });

function backendContador() {
  const b = { cuenta: 0 };
  b.fetch = async () => { b.cuenta++; return resp({ desde: 'backend' }); };
  return b;
}

test('la lista canónica es la que la app pide al cargar', () => {
  // El contrato real con la app lo revisa tests/test_copias_canonicas.py (lee web/js/api.js):
  // aquí queda la referencia legible para quien depure el Worker.
  assert.deepEqual(new Set(URLS_CANONICAS), new Set([
    '/api/status',
    '/api/config',
    '/api/official-fires',
    '/api/risk',
    '/api/incidents?hours=48',
    '/api/observations?hours=24',
  ]));
});

test('esUrlCanonica compara path + consulta exactos', () => {
  assert.equal(esUrlCanonica(u('/api/observations?hours=24')), true);
  assert.equal(esUrlCanonica(u('/api/observations?hours=6')), false);
  assert.equal(esUrlCanonica(u('/api/observations?hours=24&reliable=true')), false);
  assert.equal(esUrlCanonica(u('/api/risk')), true);
  assert.equal(esUrlCanonica(u('/api/risk?day=2026-11-10')), false);
  assert.equal(esUrlCanonica(u('/api/status?history=24')), false);
  assert.equal(esUrlCanonica(u('/api/reports/mine')), false);
});

test('sin copia en el borde y con copia reciente en R2 se responde snapshot sin llamar al contenedor', async () => {
  const k = `${ORIGEN}/api/observations?hours=24`;
  const entries = conCache();
  const backend = backendContador();
  const objeto = copia(60);
  const generada = Number(objeto.customMetadata[META_GENERADA]);
  const r = await cachedApi(req(k), ctxFalso(), 1, backend.fetch, copiaBucket(objeto));
  assert.equal(r.headers.get('x-brasa-cache'), 'snapshot');
  assert.equal(r.headers.get('x-brasa-generada'), String(Math.floor(generada / 1000)));
  assert.equal(backend.cuenta, 0);
  // La copia quedó en el borde: la próxima visita dentro de su frescura es `hit`.
  assert.ok(entries.has(k));
});

test('con copia vencida en el borde y copia más nueva en R2 también se responde snapshot', async () => {
  const k = `${ORIGEN}/api/incidents?hours=48`;
  conCache(new Map([[k, entrada(-5, -90)]]));
  const backend = backendContador();
  const r = await cachedApi(req(k), ctxFalso(), 1, backend.fetch, copiaBucket(copia(60)));
  assert.equal(r.headers.get('x-brasa-cache'), 'snapshot');
  assert.equal(backend.cuenta, 0);
});

test('con copia de más de 25 minutos se llama al contenedor como hoy', async () => {
  const k = `${ORIGEN}/api/risk`;
  conCache();
  const backend = backendContador();
  const r = await cachedApi(req(k), ctxFalso(), 1, backend.fetch, copiaBucket(copia(31 * 60)));
  assert.equal(backend.cuenta, 1);
  assert.notEqual(r.headers.get('x-brasa-cache'), 'snapshot');
});

test('sin copia en R2 se llama al contenedor como hoy', async () => {
  const k = `${ORIGEN}/api/config`;
  conCache();
  const backend = backendContador();
  const r = await cachedApi(req(k), ctxFalso(), 1, backend.fetch, copiaBucket(null));
  assert.equal(backend.cuenta, 1);
  assert.notEqual(r.headers.get('x-brasa-cache'), 'snapshot');
});

test('una URL no canónica nunca consulta R2', async () => {
  const k = `${ORIGEN}/api/risk?day=2026-11-10`;
  conCache();
  const backend = backendContador();
  let consultas = 0;
  const copias = { async get() { consultas++; return copia(60); } };
  await cachedApi(req(k), ctxFalso(), 1, backend.fetch, copias);
  assert.equal(consultas, 0);
  assert.equal(backend.cuenta, 1);
});

test('la copia de /api/status sale con la edad corregida y una fuente atrasada no se esconde', async () => {
  const k = `${ORIGEN}/api/status`;
  // Estado generado hace 5 min con GOES ya atrasada: el `stale` global es la disyunción,
  // no solo la edad global (misma regla que backend/freshness.py).
  const objeto = copia(300, {
    freshness: {
      last_ingest_at: '2026-11-10T12:00:00Z',
      age_seconds: 600,
      stale_after_s: 1800,
      stale: true,
      products: {
        GOES: { last_ok_at: '2026-11-10T11:20:00Z', age_seconds: 2400, stale_after_s: 1800, fallos_seguidos: 0, stale: true },
        FIRMS: { last_ok_at: '2026-11-10T11:58:20Z', age_seconds: 100, stale_after_s: 10800, fallos_seguidos: 0, stale: false },
      },
    },
  });
  conCache();
  const backend = backendContador();
  const r = await cachedApi(req(k), ctxFalso(), 1, backend.fetch, copiaBucket(objeto));
  assert.equal(r.headers.get('x-brasa-cache'), 'snapshot');
  const data = await r.json();
  assert.equal(data.freshness.age_seconds, 900);
  assert.equal(data.freshness.products.GOES.age_seconds, 2700);
  assert.equal(data.freshness.products.GOES.stale, true);
  assert.equal(data.freshness.products.FIRMS.age_seconds, 400);
  assert.equal(data.freshness.products.FIRMS.stale, false);
  // La edad global sigue bajo el umbral, pero GOES atrasada mantiene la píldora honesta.
  assert.equal(data.freshness.stale, true);
});

test('el estado vigente en el borde también sale con la edad corregida desde su generación', async () => {
  const k = `${ORIGEN}/api/status`;
  // Copia de R2 generada hace 9 min y recién guardada en el borde: la entrada está «vigente»
  // (dentro de su ventana), pero el dato no es de ahora y la píldora no puede decir «hace 0 min».
  const cuerpo = { freshness: { last_ingest_at: '2026-11-10T12:00:00Z', age_seconds: 3, stale_after_s: 1800, stale: false } };
  const ahora_s = Math.floor(Date.now() / 1000);
  conCache(new Map([[k, resp(cuerpo, { 'x-brasa-fresh-until': String(ahora_s + 30), 'x-brasa-generada': String(ahora_s - 540) })]]));
  const backend = backendContador();
  const r = await cachedApi(req(k), ctxFalso(), 30, backend.fetch, copiaBucket(null));
  assert.equal(r.headers.get('x-brasa-cache'), 'hit');
  const data = await r.json();
  assert.ok(data.freshness.age_seconds >= 543 && data.freshness.age_seconds <= 545);
  assert.equal(data.freshness.stale, false);
  assert.equal(backend.cuenta, 0);
});

test('una copia más vieja que lo que ya tiene el borde no la pisa ni vuelve a leer R2 dentro de la ventana', async () => {
  const k = `${ORIGEN}/api/official-fires`;
  // Entrada del borde vencida pero llena después de la copia (p. ej. por un ciclo posterior
  // o porque la escritura de esta URL falló en el último ciclo): reemplazarla retrocedería
  // datos. El contenedor falla de fondo (500), así la entrada queda vencida y es la traba
  // `copiaLastTry` la que se mide: ni R2 ni el contenedor se golpean por visita.
  conCache(new Map([[k, entrada(-5, 0)]]));
  let consultas = 0;
  const copias = { async get() { consultas++; return copia(600); } };
  const backend = backendContador();
  backend.fetch = async () => { backend.cuenta++; return new Response('malo', { status: 500 }); };
  const r1 = await cachedApi(req(k), ctxFalso(), 1, backend.fetch, copias);
  assert.equal(r1.headers.get('x-brasa-cache'), 'stale');
  assert.equal(consultas, 1);
  const r2 = await cachedApi(req(k), ctxFalso(), 1, backend.fetch, copias);
  assert.equal(r2.headers.get('x-brasa-cache'), 'stale');
  assert.equal(consultas, 1);
  assert.equal(backend.cuenta, 1);
});

test('guardarCopias escribe cada canónica bajo public/ con el instante de generación', async () => {
  const escritas = new Map();
  const bucket = {
    async put(key, cuerpo, opciones) {
      escritas.set(key, { cuerpo: new TextDecoder().decode(cuerpo), opciones });
    },
  };
  const backend = async (request) => {
    const url = new URL(request.url);
    assert.equal(request.headers.get('accept-encoding'), 'identity');
    return resp({ path: url.pathname + url.search });
  };
  const generada = 1_762_800_000_000;
  await guardarCopias(backend, bucket, generada);
  assert.equal(escritas.size, URLS_CANONICAS.length);
  for (const canonica of URLS_CANONICAS) {
    const w = escritas.get(claveCopia(canonica));
    assert.ok(w, `falta la copia de ${canonica}`);
    assert.equal(JSON.parse(w.cuerpo).path, canonica);
    assert.equal(w.opciones.customMetadata[META_GENERADA], String(generada));
    assert.equal(w.opciones.httpMetadata.contentType, 'application/json');
  }
});

test('una copia que falla se registra y no interrumpe las demás', async () => {
  const escritas = [];
  const errores = [];
  const bucket = { async put(key) { escritas.push(key); } };
  const consoleOriginal = console.error;
  console.error = (...args) => errores.push(args);
  try {
    await guardarCopias(async (request) => {
      if (new URL(request.url).pathname === '/api/risk') throw new Error('contenedor malo');
      if (new URL(request.url).pathname === '/api/config') return new Response('malo', { status: 500 });
      return resp({});
    }, bucket);
    assert.equal(escritas.length, URLS_CANONICAS.length - 2);
    assert.equal(errores.length, 2);
  } finally { console.error = consoleOriginal; }
});
