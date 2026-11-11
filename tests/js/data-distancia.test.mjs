/* VIS-03: el recorte por distancia conserva solo los puntos a `km` o menos del
 * centro; sin centro válido o sin radio devuelve la lista tal cual — es pura y
 * no toca el store ni el comportamiento de visibleObservations para otras vistas. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { filtrarPorDistancia } from '../../web/js/data.js';

// Talca como referencia: ~9 km al norte, ~34 km al este y Santiago (~250 km).
const CENTRO = { lat: -35.4264, lon: -71.6554 };
const PUNTOS = [
  { id: 1, lat: -35.35, lon: -71.65 },
  { id: 2, lat: -35.43, lon: -71.28 },
  { id: 3, lat: -33.44, lon: -70.66 },
  { id: 4 },
  { id: 5, lat: null, lon: -71.6 },
];
const ids = (r) => r.map((o) => o.id);

describe('filtrarPorDistancia (VIS-03)', () => {
  test('deja solo lo que cae dentro del radio', () => {
    assert.deepEqual(ids(filtrarPorDistancia(PUNTOS, CENTRO, 10)), [1]);
    assert.deepEqual(ids(filtrarPorDistancia(PUNTOS, CENTRO, 50)), [1, 2]);
    assert.deepEqual(ids(filtrarPorDistancia(PUNTOS, CENTRO, 100)), [1, 2]);
  });

  test('los puntos sin lat/lon finitos quedan fuera', () => {
    assert.deepEqual(ids(filtrarPorDistancia(PUNTOS, CENTRO, 10000)), [1, 2, 3]);
  });

  test('sin radio devuelve la lista tal cual', () => {
    for (const km of [0, undefined, null, NaN]) {
      assert.equal(filtrarPorDistancia(PUNTOS, CENTRO, km), PUNTOS);
    }
  });

  test('sin centro válido devuelve la lista tal cual', () => {
    for (const centro of [undefined, null, {}, { lat: 'x', lon: -71.6 }, { lat: -35.4 }]) {
      assert.equal(filtrarPorDistancia(PUNTOS, centro, 25), PUNTOS);
    }
  });

  test('entrada que no es arreglo devuelve lista vacía', () => {
    for (const bad of [null, undefined, 'algo', { points: PUNTOS }]) {
      assert.deepEqual(filtrarPorDistancia(bad, CENTRO, 25), []);
    }
  });

  test('no muta la lista original', () => {
    const antes = PUNTOS.length;
    filtrarPorDistancia(PUNTOS, CENTRO, 10);
    assert.equal(PUNTOS.length, antes);
  });
});
