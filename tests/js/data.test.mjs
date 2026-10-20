/* Pruebas de web/js/data.js con node:test: filtrado de observaciones según el store. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { isReliable, visibleObservations, loadObservations, resetObservationCache, findComuna } from '../../web/js/data.js';
import { store } from '../../web/js/store.js';

const OBS = [
  { id: 1, sensor: 'ABI', confidence: 'alta', comuna_code: 13101 },
  { id: 2, sensor: 'VIIRS', confidence: 'nominal', comuna_code: 13101 },
  { id: 3, sensor: 'MODIS', confidence: 'baja', comuna_code: 13101 },
  { id: 4, sensor: 'VIIRS', confidence: 'media', comuna_code: 13101 },
];

const setState = (obsFilter, observations = OBS) => {
  store.set('obsFilter', obsFilter);
  store.set('observations', observations);
};

const ids = () => visibleObservations().map((o) => o.id);

describe('isReliable', () => {
  test('confianzas confiables', () => {
    for (const confidence of ['alta', 'nominal', 'media']) {
      assert.equal(isReliable({ confidence }), true, confidence);
    }
  });
  test('confianzas dudosas o ausentes', () => {
    for (const confidence of ['baja', 'low', undefined]) {
      assert.equal(isReliable({ confidence }), false, confidence);
    }
    assert.equal(isReliable({}), false);
  });
});

describe('visibleObservations', () => {
  test('sin filtros muestra todo', () => {
    setState({ reliable: false, sensors: { ABI: true, VIIRS: true, MODIS: true } });
    assert.deepEqual(ids(), [1, 2, 3, 4]);
  });
  test('respeta los sensores apagados', () => {
    setState({ reliable: false, sensors: { ABI: false, VIIRS: true, MODIS: false } });
    assert.deepEqual(ids(), [2, 4]);
  });
  test('sensor sin entrada en el filtro queda visible', () => {
    setState({ reliable: false, sensors: { ABI: true } });
    assert.deepEqual(ids(), [1, 2, 3, 4]);
  });
  test('con «ocultar dudosos» solo quedan los confiables', () => {
    setState({ reliable: true, sensors: { ABI: true, VIIRS: true, MODIS: true } });
    assert.deepEqual(ids(), [1, 2, 4]);
  });
  test('combina sensores y confianza', () => {
    setState({ reliable: true, sensors: { ABI: false, VIIRS: true, MODIS: true } });
    assert.deepEqual(ids(), [2, 4]);
  });
  test('sin observaciones devuelve lista vacía', () => {
    setState({ reliable: false, sensors: {} }, []);
    assert.deepEqual(visibleObservations(), []);
    store.set('observations', null);
    assert.deepEqual(visibleObservations(), []);
  });
  test('descarta las detecciones sin comuna chilena', () => {
    setState({ reliable: false, sensors: { ABI: true, VIIRS: true, MODIS: true } }, [
      { id: 1, sensor: 'ABI', confidence: 'alta', comuna_code: 13101 },
      { id: 2, sensor: 'VIIRS', confidence: 'nominal', comuna_code: null },
    ]);
    assert.deepEqual(ids(), [1]);
  });
  test('con «ocultar dudosos» sigue mandando la confianza entre las chilenas', () => {
    setState({ reliable: true, sensors: { ABI: true, VIIRS: true, MODIS: true } }, [
      { id: 1, sensor: 'ABI', confidence: 'alta', comuna_code: 13101 },
      { id: 2, sensor: 'VIIRS', confidence: 'baja', comuna_code: 13101 },
      { id: 3, sensor: 'VIIRS', confidence: 'nominal', comuna_code: null },
    ]);
    assert.deepEqual(ids(), [1]);
  });
});

describe('loadObservations: un corte idéntico no se vuelve a entregar', () => {
  const PAYLOAD = { data_as_of: '2026-10-19T10:00:00Z', points: [{ id: 1, comuna_code: 13101 }], truncated: false, limit: 0 };
  let responses;

  const jsonRes = (body) => new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });

  beforeEach(() => {
    resetObservationCache();
    store.set('obsHours', 24);
    responses = [];
    globalThis.fetch = async () => responses.shift();
  });

  afterEach(() => {
    delete globalThis.fetch;
    store.set('obsHours', 24);
  });

  test('la primera llamada devuelve datos', async () => {
    responses.push(jsonRes(PAYLOAD));
    assert.deepEqual(await loadObservations(), PAYLOAD);
  });

  test('la segunda idéntica devuelve null', async () => {
    responses.push(jsonRes(PAYLOAD), jsonRes(PAYLOAD));
    assert.deepEqual(await loadObservations(), PAYLOAD);
    assert.equal(await loadObservations(), null);
  });

  test('si cambia data_as_of devuelve datos', async () => {
    const newer = { ...PAYLOAD, data_as_of: '2026-10-19T10:05:00Z' };
    responses.push(jsonRes(PAYLOAD), jsonRes(newer));
    await loadObservations();
    assert.deepEqual(await loadObservations(), newer);
  });

  test('si cambia obsHours devuelve datos', async () => {
    responses.push(jsonRes(PAYLOAD), jsonRes(PAYLOAD));
    await loadObservations();
    store.set('obsHours', 48);
    assert.deepEqual(await loadObservations(), PAYLOAD);
  });

  test('si cambia la cantidad de puntos devuelve datos', async () => {
    const more = { ...PAYLOAD, points: [{ id: 1, comuna_code: 13101 }, { id: 2, comuna_code: 13101 }] };
    responses.push(jsonRes(PAYLOAD), jsonRes(more));
    await loadObservations();
    assert.deepEqual(await loadObservations(), more);
  });

  test('descarta los puntos sin comuna chilena y conserva el corte del servidor', async () => {
    const mixed = {
      ...PAYLOAD,
      points: [{ id: 1, comuna_code: 13101 }, { id: 2, comuna_code: null }],
      truncated: true,
      limit: 20000,
    };
    responses.push(jsonRes(mixed));
    const data = await loadObservations();
    assert.deepEqual(data.points, [{ id: 1, comuna_code: 13101 }]);
    assert.equal(data.data_as_of, PAYLOAD.data_as_of);
    assert.equal(data.truncated, true);
    assert.equal(data.limit, 20000);
  });

  test('si cambia truncated devuelve datos', async () => {
    const cut = { ...PAYLOAD, truncated: true, limit: 20000 };
    responses.push(jsonRes(PAYLOAD), jsonRes(cut));
    await loadObservations();
    assert.deepEqual(await loadObservations(), cut);
    assert.equal(store.get('obsTruncated'), 20000);
  });
});

describe('findComuna', () => {
  const COMUNAS = [
    { code: 1, name: 'Quilpué', region: 'Valparaíso' },
    { code: 2, name: 'Quilicura', region: 'Metropolitana' },
    { code: 3, name: 'Ñuñoa', region: 'Metropolitana' },
    { code: 4, name: 'Alto Biobío', region: 'Biobío' },
    { code: 5, name: 'Ovalle', region: 'Coquimbo' },
    { code: 6, name: 'Valdivia', region: 'Los Ríos' },
    { code: 7, name: 'Vallenar', region: 'Atacama' },
    { code: 8, name: 'Valparaíso', region: 'Valparaíso' },
  ];
  const names = (r) => r.matches.map((c) => c.name);

  test('encuentra el nombre exacto aunque falte la tilde, sobren mayúsculas o espacios', () => {
    for (const text of ['Quilpué', 'quilpue', 'QUILPUE', 'quilpué ', ' Quilpue']) {
      const r = findComuna(COMUNAS, text);
      assert.equal(r.exact?.name, 'Quilpué', text);
    }
  });

  test('la eñe y la tilde no bloquean «Ñuñoa»', () => {
    assert.equal(findComuna(COMUNAS, 'Ñuñoa').exact?.code, 3);
    assert.equal(findComuna(COMUNAS, 'nunoa').exact?.code, 3);
  });

  test('«Biobío» encuentra «Alto Biobío» como candidata', () => {
    for (const text of ['Biobío', 'biobio']) {
      const r = findComuna(COMUNAS, text);
      assert.equal(r.exact, null, text);
      assert.deepEqual(names(r), ['Alto Biobío']);
    }
  });

  test('parcial «val»: prefijo primero, después las que lo contienen, por nombre', () => {
    const r = findComuna(COMUNAS, 'val');
    assert.equal(r.exact, null);
    assert.deepEqual(names(r), ['Valdivia', 'Vallenar', 'Valparaíso', 'Ovalle']);
  });

  test('sin coincidencia devuelve listas vacías', () => {
    assert.deepEqual(findComuna(COMUNAS, 'zzz'), { exact: null, matches: [] });
  });

  test('texto vacío o nulo devuelve listas vacías', () => {
    for (const text of ['', '   ', null, undefined]) {
      assert.deepEqual(findComuna(COMUNAS, text), { exact: null, matches: [] });
    }
  });

  test('matches nunca pasa de 8', () => {
    const many = Array.from({ length: 10 }, (_, i) => ({ code: i, name: `San ${String(i).padStart(2, '0')}` }));
    assert.equal(findComuna(many, 'san').matches.length, 8);
  });

  test('lista nula o vacía no explota', () => {
    assert.deepEqual(findComuna(null, 'quilpue'), { exact: null, matches: [] });
    assert.deepEqual(findComuna([], 'quilpue'), { exact: null, matches: [] });
  });
});
