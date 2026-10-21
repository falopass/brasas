/* FIX-120: el filtro de focos tolera estado viejo, incompleto o que no sea objeto;
 * un filtro roto no puede dejar el mapa y la lista vacíos ni lanzar en plena pintada. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizarFiltro, visibleObservations } from '../../web/js/data.js';
import { store } from '../../web/js/store.js';

const DEFAULT = { reliable: false, sensors: { ABI: true, VIIRS: true, MODIS: true } };

const OBS = [
  { id: 1, sensor: 'ABI', confidence: 'alta', comuna_code: 13101 },
  { id: 2, sensor: 'VIIRS', confidence: 'nominal', comuna_code: 13101 },
  { id: 3, sensor: 'MODIS', confidence: 'media', comuna_code: 13101 },
];
const ids = () => visibleObservations().map((o) => o.id);

describe('normalizarFiltro', () => {
  test('lo que no es objeto devuelve el filtro por defecto', () => {
    for (const f of [undefined, null, 'viejo', 7, true]) {
      assert.deepEqual(normalizarFiltro(f), DEFAULT, String(f));
    }
  });

  test('objeto vacío devuelve el filtro por defecto', () => {
    assert.deepEqual(normalizarFiltro({}), DEFAULT);
  });

  test('mezcla los sensores guardados y descarta los desconocidos', () => {
    assert.deepEqual(normalizarFiltro({ sensors: { ABI: false } }), {
      reliable: false,
      sensors: { ABI: false, VIIRS: true, MODIS: true },
    });
    assert.deepEqual(normalizarFiltro({ sensors: { OTRO: false } }), DEFAULT);
  });

  test('solo cuentan los booleanos', () => {
    assert.deepEqual(normalizarFiltro({ reliable: 'sí' }), DEFAULT);
    assert.deepEqual(normalizarFiltro({ reliable: true, sensors: { VIIRS: 'no' } }), {
      reliable: true,
      sensors: { ABI: true, VIIRS: true, MODIS: true },
    });
  });

  test('no comparte el objeto por defecto entre llamadas', () => {
    normalizarFiltro(null).sensors.ABI = false;
    assert.deepEqual(normalizarFiltro(null), DEFAULT);
  });
});

describe('visibleObservations con estado viejo o roto', () => {
  test('sin obsFilter guardado muestra todos los focos', () => {
    store.set('obsFilter', undefined);
    store.set('observations', OBS);
    assert.deepEqual(ids(), [1, 2, 3]);
  });

  test('un obsFilter vacío no vacía la lista', () => {
    store.set('obsFilter', {});
    store.set('observations', OBS);
    assert.deepEqual(ids(), [1, 2, 3]);
  });

  test('un filtro viejo sin «sensors» no lanza', () => {
    store.set('obsFilter', { reliable: true });
    store.set('observations', OBS);
    assert.deepEqual(ids(), [1, 2, 3]);
  });

  test('respeta los sensores apagados aunque falten claves', () => {
    store.set('obsFilter', { sensors: { ABI: false } });
    store.set('observations', OBS);
    assert.deepEqual(ids(), [2, 3]);
  });

  test('observations que no es arreglo devuelve lista vacía', () => {
    store.set('obsFilter', undefined);
    for (const bad of [null, undefined, 'algo', { points: OBS }]) {
      store.set('observations', bad);
      assert.deepEqual(visibleObservations(), []);
    }
  });

  test('elementos sin confidence no lanzan ni se cuelan con «ocultar dudosos»', () => {
    store.set('obsFilter', { reliable: true });
    store.set('observations', [...OBS, { id: 4, sensor: 'VIIRS', comuna_code: 13101 }]);
    assert.deepEqual(ids(), [1, 2, 3]);
  });
});
