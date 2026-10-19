/* Pruebas de web/js/pantalla-rotacion.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRotation } from '../../web/js/pantalla-rotacion.js';

describe('parseRotation', () => {
  test('sin parámetros: lista vacía y 45 s por defecto', () => {
    assert.deepEqual(parseRotation(''), { params: [], segundos: 45 });
    assert.deepEqual(parseRotation('?'), { params: [], segundos: 45 });
    assert.deepEqual(parseRotation('?comuna=13101'), { params: [], segundos: 45 });
  });
  test('una sola comuna', () => {
    assert.deepEqual(parseRotation('?comunas=13101'), { params: ['13101'], segundos: 45 });
  });
  test('varias comunas, con código y con nombre', () => {
    assert.deepEqual(parseRotation('?comunas=13101,Penalolen,13201'),
      { params: ['13101', 'Penalolen', '13201'], segundos: 45 });
    assert.deepEqual(parseRotation('?comunas=13101, San%20Joaqu%C3%ADn , 13202'),
      { params: ['13101', 'San Joaquín', '13202'], segundos: 45 });
  });
  test('vacíos y duplicados (sin tildes ni mayúsculas) se eliminan', () => {
    assert.deepEqual(parseRotation('?comunas=, ,,'), { params: [], segundos: 45 });
    assert.deepEqual(parseRotation('?comunas=Penalolen,penalolén,PENALOLEN,13101'),
      { params: ['Penalolen', '13101'], segundos: 45 });
  });
  test('rotar dentro del rango se respeta', () => {
    assert.equal(parseRotation('?comunas=a,b&rotar=30').segundos, 30);
    assert.equal(parseRotation('?rotar=5').segundos, 5);
    assert.equal(parseRotation('?rotar=300').segundos, 300);
  });
  test('rotar fuera de rango se acota o cae al defecto', () => {
    assert.equal(parseRotation('?rotar=9999').segundos, 300);
    assert.equal(parseRotation('?rotar=2').segundos, 5);
    assert.equal(parseRotation('?rotar=0').segundos, 45);
    assert.equal(parseRotation('?rotar=-20').segundos, 45);
    assert.equal(parseRotation('?rotar=abc').segundos, 45);
    assert.equal(parseRotation('?rotar=').segundos, 45);
  });
});
