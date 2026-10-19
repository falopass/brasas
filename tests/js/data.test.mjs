/* Pruebas de web/js/data.js con node:test: filtrado de observaciones según el store. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { isReliable, visibleObservations } from '../../web/js/data.js';
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
