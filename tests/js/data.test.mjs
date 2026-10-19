/* Pruebas de web/js/data.js con node:test: filtrado de observaciones según el store. */
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { isReliable, visibleObservations, loadObservations, resetObservationCache } from '../../web/js/data.js';
import { store } from '../../web/js/store.js';

const OBS = [
  { id: 1, sensor: 'ABI', confidence: 'alta' },
  { id: 2, sensor: 'VIIRS', confidence: 'nominal' },
  { id: 3, sensor: 'MODIS', confidence: 'baja' },
  { id: 4, sensor: 'VIIRS', confidence: 'media' },
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
});

describe('loadObservations: un corte idéntico no se vuelve a entregar', () => {
  const PAYLOAD = { data_as_of: '2026-10-19T10:00:00Z', points: [{ id: 1 }], truncated: false, limit: 0 };
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
    const more = { ...PAYLOAD, points: [{ id: 1 }, { id: 2 }] };
    responses.push(jsonRes(PAYLOAD), jsonRes(more));
    await loadObservations();
    assert.deepEqual(await loadObservations(), more);
  });

  test('si cambia truncated devuelve datos', async () => {
    const cut = { ...PAYLOAD, truncated: true, limit: 20000 };
    responses.push(jsonRes(PAYLOAD), jsonRes(cut));
    await loadObservations();
    assert.deepEqual(await loadObservations(), cut);
    assert.equal(store.get('obsTruncated'), 20000);
  });
});
