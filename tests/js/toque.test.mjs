/* Pruebas de la elección del objetivo de un toque (MAPA-157): elegirObjetivo es
   pura — qué capa gana entre varias que el dedo cubrió a la vez. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { elegirObjetivo, PRIORIDAD_TOQUE } from '../../web/js/capas.js';

const punto = (capa, distPx = 0, count = 0) => ({
  capa,
  distPx,
  feature: { type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: count > 1 ? { count } : {} },
});

describe('elegirObjetivo (MAPA-157)', () => {
  test('comuna con peligro y un foco a 6 px: gana el foco', () => {
    const gana = elegirObjetivo([punto('risk-fill'), punto('detections', 6)]);
    assert.equal(gana.capa, 'detections');
  });
  test('cuadro GOES y punto VIIRS: gana el VIIRS', () => {
    const gana = elegirObjetivo([punto('goes-pixels'), punto('detections', 3)]);
    assert.equal(gana.capa, 'detections');
  });
  test('celda y anillo a la misma prioridad: gana el más cercano', () => {
    const gana = elegirObjetivo([punto('incident-rings', 9), punto('detections', 4, 12)]);
    assert.equal(gana.capa, 'detections');
    const gana2 = elegirObjetivo([punto('incident-rings', 2), punto('detections', 9, 12)]);
    assert.equal(gana2.capa, 'incident-rings');
  });
  test('CONAF y un foco: gana CONAF', () => {
    const gana = elegirObjetivo([punto('detections', 1), punto('official', 8)]);
    assert.equal(gana.capa, 'official');
  });
  test('lista vacía devuelve null', () => {
    assert.equal(elegirObjetivo([]), null);
    assert.equal(elegirObjetivo(), null);
  });
  test('etiqueta y contorno del incidente comparten la prioridad del anillo (MAPA-163)', () => {
    assert.equal(PRIORIDAD_TOQUE['incident-labels'], PRIORIDAD_TOQUE['incident-rings']);
    assert.equal(PRIORIDAD_TOQUE['incident-hulls-line'], PRIORIDAD_TOQUE['incident-rings']);
    assert.equal(PRIORIDAD_TOQUE['official-labels'], PRIORIDAD_TOQUE.official);
    // Un foco bajo la etiqueta sigue ganando: abre su ficha, no la del incidente.
    const gana = elegirObjetivo([punto('incident-labels'), punto('detections', 5)]);
    assert.equal(gana.capa, 'detections');
  });
  test('una capa no listada queda última (prioridad 9)', () => {
    assert.equal(elegirObjetivo([punto('otra-cosa'), punto('risk-fill', 10)]).capa, 'risk-fill');
    assert.equal(PRIORIDAD_TOQUE.official, 0);
    assert.equal(PRIORIDAD_TOQUE['goes-pixels'], 3);
  });
});
