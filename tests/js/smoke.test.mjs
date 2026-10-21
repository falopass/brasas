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

const HANG = Symbol('nunca responde');

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
    globalThis.fetch = (url, init) => {
      calls.push(url);
      const next = responses.shift();
      if (next === HANG) {
        return new Promise((_, reject) => {
          init.signal.addEventListener('abort', () => reject(init.signal.reason ?? new Error('abort')));
        });
      }
      if (next instanceof Error) return Promise.reject(next);
      return Promise.resolve(next);
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

  test('500 sin detail → mensaje con el código', async () => {
    responses.push(jsonRes(500, {}));
    const err = await loadSmoke().catch((e) => e);
    assert.match(err.message, /error 500/);
  });

  test('200 con HTML → mensaje de cuerpo inválido', async () => {
    responses.push(new Response('<html>caída del proxy</html>', {
      status: 200,
      headers: { 'content-type': 'text/html' },
    }));
    const err = await loadSmoke().catch((e) => e);
    assert.equal(err.message, 'El humo de GOES no está disponible ahora.');
  });

  test('FeatureCollection vacío → devuelve el cuerpo', async () => {
    responses.push(jsonRes(200, { type: 'FeatureCollection', features: [] }));
    const data = await loadSmoke();
    assert.deepEqual(data.features, []);
  });

  test('cuelgue con AbortSignal.timeout → «tardó demasiado»', async (t) => {
    // AbortSignal.timeout usa un temporizador interno con unref en Node: inyectamos
    // una señal manual para disparar el abort de forma determinista.
    const real = AbortSignal.timeout;
    const ctrl = new AbortController();
    let pedido;
    AbortSignal.timeout = (ms) => { pedido = ms; return ctrl.signal; };
    t.after(() => { AbortSignal.timeout = real; });
    responses.push(HANG);
    const pending = loadSmoke();
    assert.equal(pedido, 12_000); // la capa pide el tope de 12 s
    ctrl.abort(new DOMException('tiempo agotado', 'TimeoutError'));
    const err = await pending.catch((e) => e);
    assert.match(err.message, /tardó demasiado en responder/);
  });

  test('cuelgue sin AbortSignal.timeout → el respaldo aborta al tope', async (t) => {
    t.mock.timers.enable();
    const real = AbortSignal.timeout;
    AbortSignal.timeout = undefined; // fuerza el respaldo con AbortController
    t.after(() => { AbortSignal.timeout = real; });
    responses.push(HANG);
    const pending = loadSmoke();
    t.mock.timers.tick(12_000);
    const err = await pending.catch((e) => e);
    assert.match(err.message, /tardó demasiado en responder/);
  });

  test('respuesta a tiempo con el respaldo → limpia el temporizador', async (t) => {
    t.mock.timers.enable();
    const real = AbortSignal.timeout;
    AbortSignal.timeout = undefined;
    t.after(() => { AbortSignal.timeout = real; });
    let signal;
    globalThis.fetch = (url, init) => {
      calls.push(url);
      signal = init.signal;
      return Promise.resolve(jsonRes(200, FC));
    };
    const data = await loadSmoke();
    assert.equal(data.type, 'FeatureCollection');
    t.mock.timers.tick(120_000); // si el temporizador quedó vivo, abortaría tarde
    assert.equal(signal.aborted, false);
  });
});

describe('paleta', () => {
  test('un gris por tema y opacidad baja', () => {
    assert.ok(SMOKE_COLOR.dark && SMOKE_COLOR.light);
    assert.ok(SMOKE_OPACITY > 0 && SMOKE_OPACITY <= 0.5);
  });
});
