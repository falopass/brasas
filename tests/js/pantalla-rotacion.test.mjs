/* Pruebas de web/js/pantalla-rotacion.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRotation, MAX_COMUNAS } from '../../web/js/pantalla-rotacion.js';

describe('parseRotation', () => {
  test('sin parámetros: lista vacía y 45 s por defecto', () => {
    assert.deepEqual(parseRotation(''), { params: [], segundos: 45, recortadas: 0 });
    assert.deepEqual(parseRotation('?'), { params: [], segundos: 45, recortadas: 0 });
    assert.deepEqual(parseRotation('?comuna=13101'), { params: [], segundos: 45, recortadas: 0 });
  });
  test('una sola comuna', () => {
    assert.deepEqual(parseRotation('?comunas=13101'), { params: ['13101'], segundos: 45, recortadas: 0 });
  });
  test('varias comunas, con código y con nombre', () => {
    assert.deepEqual(parseRotation('?comunas=13101,Penalolen,13201'),
      { params: ['13101', 'Penalolen', '13201'], segundos: 45, recortadas: 0 });
    assert.deepEqual(parseRotation('?comunas=13101, San%20Joaqu%C3%ADn , 13202'),
      { params: ['13101', 'San Joaquín', '13202'], segundos: 45, recortadas: 0 });
  });
  test('vacíos y duplicados (sin tildes ni mayúsculas) se eliminan', () => {
    assert.deepEqual(parseRotation('?comunas=, ,,'), { params: [], segundos: 45, recortadas: 0 });
    assert.deepEqual(parseRotation('?comunas=Penalolen,penalolén,PENALOLEN,13101'),
      { params: ['Penalolen', '13101'], segundos: 45, recortadas: 0 });
  });
  test('el código repetido se colapsa aunque llegue separado', () => {
    assert.deepEqual(parseRotation('?comunas=13101,13101,Puente%20Alto'),
      { params: ['13101', 'Puente Alto'], segundos: 45, recortadas: 0 });
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

  describe('tope de la lista (PANTALLA-02)', () => {
    test('más de MAX_COMUNAS se recorta y queda contado', () => {
      const lista = Array.from({ length: 30 }, (_, i) => String(13100 + i)).join(',');
      const out = parseRotation(`?comunas=${lista}`);
      assert.equal(out.params.length, 24);
      assert.equal(MAX_COMUNAS, 24);
      assert.equal(out.recortadas, 6);
      assert.deepEqual(out.params[0], '13100');
    });
    test('los duplicados no gastan el tope', () => {
      const lista = Array.from({ length: 30 }, (_, i) => String(13100 + (i % 10))).join(',');
      const out = parseRotation(`?comunas=${lista}`);
      assert.equal(out.params.length, 10);
      assert.equal(out.recortadas, 0);
    });
  });

  describe('deduplicación por comuna resuelta (resolver)', () => {
    const resolver = (t) => (t === '13101' || t === 'Puente Alto' ? 13101 : null);
    test('código y nombre de la misma comuna cuentan una sola vez', () => {
      const out = parseRotation('?comunas=13101,Puente%20Alto', resolver);
      assert.equal(out.params.length, 1);
      assert.deepEqual(out.params, ['13101']);
    });
    test('el nombre primero también colapsa el código', () => {
      const out = parseRotation('?comunas=Puente%20Alto,13101,Santiago', resolver);
      assert.deepEqual(out.params, ['Puente Alto', 'Santiago']);
    });
    test('sin resolver el contrato no cambia: código y nombre son dos entradas', () => {
      assert.equal(parseRotation('?comunas=13101,Puente Alto').params.length, 2);
    });
    test('un trozo que el resolver no conoce se deduplica por su texto', () => {
      const nulo = () => null;
      assert.deepEqual(parseRotation('?comunas=Nope,nope,13101', nulo).params, ['Nope', '13101']);
    });
  });
});
