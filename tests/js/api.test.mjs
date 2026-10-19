/* Pruebas de web/js/api.js con node:test, sin navegador ni dependencias.
 * fetch y localStorage se simulan en globalThis; cada test los restaura. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, request, api } from '../../web/js/api.js';
import { storage } from '../../web/js/util.js';

let store;
let calls;
let responses;

const jsonRes = (status, body) => new Response(JSON.stringify(body), {
  status,
  headers: { 'content-type': 'application/json' },
});

beforeEach(() => {
  store = new Map();
  calls = [];
  responses = [];
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    const next = responses.shift();
    if (next instanceof Error) throw next;
    return next;
  };
});

afterEach(() => {
  delete globalThis.fetch;
  delete globalThis.localStorage;
});

describe('parse: mapeo de errores', () => {
  test('detail string → mensaje exacto, status y code undefined', async () => {
    responses.push(jsonRes(400, { detail: 'El parámetro hours es obligatorio' }));
    const err = await request('/api/x').catch((e) => e);
    assert.ok(err instanceof ApiError);
    assert.equal(err.message, 'El parámetro hours es obligatorio');
    assert.equal(err.status, 400);
    assert.equal(err.code, undefined);
  });

  test('detail.message y detail.code se propagan', async () => {
    responses.push(jsonRes(403, { detail: { message: 'Token inválido', code: 'BAD_TOKEN' } }));
    const err = await request('/api/x').catch((e) => e);
    assert.equal(err.message, 'Token inválido');
    assert.equal(err.status, 403);
    assert.equal(err.code, 'BAD_TOKEN');
  });

  test('422 con lista de validación → «Dato inválido: campos»', async () => {
    responses.push(jsonRes(422, { detail: [
      { loc: ['body', 'lat'], msg: 'field required' },
      { loc: ['body', 'lon'], msg: 'field required' },
    ] }));
    const err = await request('/api/x').catch((e) => e);
    assert.equal(err.message, 'Dato inválido: lat, lon');
    assert.equal(err.status, 422);
  });

  test('500 sin JSON → mensaje genérico de servidor', async () => {
    responses.push(new Response('boom', { status: 500, headers: { 'content-type': 'text/plain' } }));
    const err = await request('/api/x').catch((e) => e);
    assert.equal(err.message, 'El servidor no pudo completar la solicitud.');
    assert.equal(err.status, 500);
  });

  test('4xx sin detail reconocible → «Error N»', async () => {
    responses.push(new Response('no', { status: 404, headers: { 'content-type': 'text/plain' } }));
    const err = await request('/api/x').catch((e) => e);
    assert.equal(err.message, 'Error 404');
  });
});

describe('request: conexión y cuerpo', () => {
  test('fetch rechazado → ApiError OFFLINE con status 0', async () => {
    responses.push(new TypeError('fetch failed'));
    const err = await request('/api/x').catch((e) => e);
    assert.ok(err instanceof ApiError);
    assert.equal(err.code, 'OFFLINE');
    assert.equal(err.status, 0);
    assert.equal(err.message, 'Sin conexión con el servidor de BRASA.');
  });

  test('AbortError se propaga sin envolver', async () => {
    const abort = new Error('aborted');
    abort.name = 'AbortError';
    responses.push(abort);
    const err = await request('/api/x').catch((e) => e);
    assert.ok(!(err instanceof ApiError));
    assert.equal(err.name, 'AbortError');
  });

  test('JSON inválido en respuesta ok → null sin lanzar', async () => {
    responses.push(new Response('{{{', { status: 200, headers: { 'content-type': 'application/json' } }));
    assert.equal(await request('/api/x'), null);
  });

  test('respuesta ok devuelve el cuerpo parseado', async () => {
    responses.push(jsonRes(200, { ok: true }));
    assert.deepEqual(await request('/api/x'), { ok: true });
  });

  test('body objeto → JSON con Content-Type', async () => {
    responses.push(jsonRes(200, {}));
    await request('/api/x', { method: 'POST', body: { a: 1 } });
    assert.equal(calls[0].init.body, '{"a":1}');
    assert.equal(calls[0].init.headers['Content-Type'], 'application/json');
  });
});

describe('request: auth y reintento ante 401', () => {
  test('auth:true envía X-Brasa-Token con el token guardado', async () => {
    storage.set('token', 'tok1');
    responses.push(jsonRes(200, {}));
    await request('/api/x', { auth: true });
    assert.equal(calls[0].init.headers['X-Brasa-Token'], 'tok1');
  });

  test('sin token guardado registra el dispositivo primero (POST /api/subscribers)', async () => {
    responses.push(jsonRes(200, { token: 'nuevo' }));
    responses.push(jsonRes(200, {}));
    await request('/api/x', { auth: true });
    assert.equal(calls[0].url, '/api/subscribers');
    assert.equal(calls[0].init.method, 'POST');
    assert.equal(calls[1].init.headers['X-Brasa-Token'], 'nuevo');
    assert.equal(storage.get('token'), 'nuevo');
  });

  test('401 con auth limpia el token y reintenta una vez', async () => {
    storage.set('token', 'viejo');
    responses.push(jsonRes(401, { detail: 'Token inválido' }));
    responses.push(jsonRes(200, { token: 'nuevo' })); // re-registro del dispositivo
    responses.push(jsonRes(200, { ok: true }));
    const out = await request('/api/x', { auth: true });
    assert.deepEqual(out, { ok: true });
    assert.equal(calls.length, 3);
    assert.equal(calls[0].init.headers['X-Brasa-Token'], 'viejo');
    assert.equal(calls[1].url, '/api/subscribers');
    assert.equal(calls[2].init.headers['X-Brasa-Token'], 'nuevo');
    assert.equal(storage.get('token'), 'nuevo');
  });

  test('segundo 401 no reintenta: devuelve el error', async () => {
    storage.set('token', 'viejo');
    responses.push(jsonRes(401, { detail: 'Token inválido' }));
    responses.push(jsonRes(200, { token: 'nuevo' }));
    responses.push(jsonRes(401, { detail: 'Sigue inválido' }));
    const err = await request('/api/x', { auth: true }).catch((e) => e);
    assert.equal(err.status, 401);
    assert.equal(err.message, 'Sigue inválido');
    assert.equal(calls.length, 3);
  });
});

describe('api: endpoints', () => {
  test('construye las rutas esperadas', async () => {
    responses.push(jsonRes(200, {}), jsonRes(200, {}), jsonRes(200, {}));
    await api.observations(24, true);
    await api.shared('a b');
    await api.risk('2024-01-15');
    assert.equal(calls[0].url, '/api/observations?hours=24&reliable=true');
    assert.equal(calls[1].url, '/api/shared/a%20b');
    assert.equal(calls[2].url, '/api/risk?day=2024-01-15');
  });
});
