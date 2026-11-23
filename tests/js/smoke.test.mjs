/* Pruebas de web/js/smoke.js con node:test, sin navegador ni dependencias.
 * fetch se simula en globalThis; cada test lo restaura. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  loadSmoke,
  SMOKE_COLOR,
  SMOKE_OPACITY,
  SMOKE_DENSITY_COLOR,
  SMOKE_DENSITY_OPACITY,
  smokeFillColorExpr,
  smokeFillOpacityExpr,
  smokeDensitySummary,
} from '../../web/js/smoke.js';

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

describe('expresiones por densidad (DET-48)', () => {
  for (const theme of ['dark', 'light']) {
    test(`smokeFillColorExpr(${theme}) usa match sobre density con respaldo a SMOKE_COLOR`, () => {
      const expr = smokeFillColorExpr(theme);
      assert.deepEqual(expr, [
        'match',
        ['get', 'density'],
        'tenue', SMOKE_DENSITY_COLOR[theme].tenue,
        'moderado', SMOKE_DENSITY_COLOR[theme].moderado,
        'denso', SMOKE_DENSITY_COLOR[theme].denso,
        SMOKE_COLOR[theme],
      ]);
      assert.notEqual(SMOKE_DENSITY_COLOR[theme].tenue, SMOKE_DENSITY_COLOR[theme].denso);
    });
  }

  test('smokeFillColorExpr distingue tema oscuro de claro y cae a oscuro con tema desconocido', () => {
    assert.notDeepEqual(smokeFillColorExpr('dark'), smokeFillColorExpr('light'));
    assert.deepEqual(smokeFillColorExpr('otro'), smokeFillColorExpr('dark'));
  });

  test('smokeFillOpacityExpr escala tenue < moderado < denso con respaldo a SMOKE_OPACITY', () => {
    const expr = smokeFillOpacityExpr();
    assert.deepEqual(expr, [
      'match',
      ['get', 'density'],
      'tenue', SMOKE_DENSITY_OPACITY.tenue,
      'moderado', SMOKE_DENSITY_OPACITY.moderado,
      'denso', SMOKE_DENSITY_OPACITY.denso,
      SMOKE_OPACITY,
    ]);
    assert.ok(SMOKE_DENSITY_OPACITY.tenue > 0);
    assert.ok(SMOKE_DENSITY_OPACITY.tenue < SMOKE_DENSITY_OPACITY.moderado);
    assert.ok(SMOKE_DENSITY_OPACITY.moderado < SMOKE_DENSITY_OPACITY.denso);
    assert.ok(SMOKE_DENSITY_OPACITY.denso <= 0.6);
    assert.equal(expr.at(-1), SMOKE_OPACITY);
  });
});

describe('smokeDensitySummary', () => {
  test('cuenta polígonos por densidad y marca hasAod cuando al menos uno trae AOD', () => {
    const fc = {
      type: 'FeatureCollection',
      aod_available: true,
      features: [
        { type: 'Feature', properties: { density: 'tenue', aod_p90: 0.25 } },
        { type: 'Feature', properties: { density: 'tenue', aod_p90: 0.35 } },
        { type: 'Feature', properties: { density: 'moderado', aod_p90: 0.7 } },
        { type: 'Feature', properties: { density: 'denso', aod_p90: 1.4 } },
        { type: 'Feature', properties: { density: null, aod_p90: null } },
        { type: 'Feature', properties: {} },
      ],
    };
    assert.deepEqual(smokeDensitySummary(fc), {
      hasAod: true,
      tenue: 2,
      moderado: 1,
      denso: 1,
      sinAod: 2,
    });
  });

  test('sin densidad en los polígonos (noche o nubosidad) → hasAod false y todo en sinAod', () => {
    const fc = {
      type: 'FeatureCollection',
      aod_available: false,
      features: [
        { type: 'Feature', properties: { density: null } },
        { type: 'Feature', properties: { age_min: 15 } },
      ],
    };
    assert.deepEqual(smokeDensitySummary(fc), {
      hasAod: false,
      tenue: 0,
      moderado: 0,
      denso: 0,
      sinAod: 2,
    });
  });

  test('colección vacía o entrada nula → contadores en cero y hasAod false', () => {
    const cero = { hasAod: false, tenue: 0, moderado: 0, denso: 0, sinAod: 0 };
    assert.deepEqual(smokeDensitySummary({ type: 'FeatureCollection', features: [] }), cero);
    assert.deepEqual(smokeDensitySummary(null), cero);
    assert.deepEqual(smokeDensitySummary(undefined), cero);
  });
});
