/* Pruebas de web/js/buscador.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buscarComunas, normalizar } from '../../web/js/buscador.js';

const INDEX = JSON.parse(readFileSync(new URL('../../web/data/comunas-index.json', import.meta.url), 'utf8'));
const nombres = (hits) => hits.map((c) => c.name);

describe('normalizar', () => {
  test('pasa a minúsculas y quita los diacríticos', () => {
    assert.equal(normalizar('Ñuble'), 'nuble');
    assert.equal(normalizar('SAN CLEMENTE'), 'san clemente');
    assert.equal(normalizar('Talca'), 'talca');
  });
  test('no falla con vacío ni con valores ausentes', () => {
    assert.equal(normalizar(''), '');
    assert.equal(normalizar(null), '');
    assert.equal(normalizar(undefined), '');
  });
});

describe('buscar comunas en el índice real (MAPA-21)', () => {
  test('«talca» encuentra Talca primero', () => {
    assert.equal(buscarComunas(INDEX, 'talca')[0].name, 'Talca');
  });
  test('«Talca» y «TALCA» dan lo mismo', () => {
    assert.deepEqual(nombres(buscarComunas(INDEX, 'Talca')), nombres(buscarComunas(INDEX, 'TALCA')));
  });
  test('«ñuble» y «nuble» encuentran comunas de Ñuble', () => {
    for (const texto of ['ñuble', 'nuble', 'ÑUBLE']) {
      const hits = buscarComunas(INDEX, texto);
      assert.ok(hits.length > 0, `«${texto}» no devolvió comunas`);
      assert.ok(hits.every((c) => c.region === 'Ñuble'), `«${texto}» devolvió otra región`);
    }
  });
  test('«san clemente» encuentra San Clemente', () => {
    assert.equal(buscarComunas(INDEX, 'san clemente')[0].name, 'San Clemente');
  });
  test('«scl» lleva a Santiago (código del aeropuerto)', () => {
    assert.equal(buscarComunas(INDEX, 'scl')[0].name, 'Santiago');
  });
  test('texto vacío devuelve lista vacía', () => {
    assert.deepEqual(buscarComunas(INDEX, ''), []);
    assert.deepEqual(buscarComunas(INDEX, '   '), []);
  });
  test('un texto sin coincidencias devuelve [] y no lanza', () => {
    assert.deepEqual(buscarComunas(INDEX, 'zzzz'), []);
    assert.deepEqual(buscarComunas(INDEX, 'constructor'), []);
    assert.deepEqual(buscarComunas(INDEX, '__proto__'), []);
    assert.deepEqual(buscarComunas(null, 'talca'), []);
  });
  test('devuelve como máximo 8 resultados', () => {
    assert.ok(buscarComunas(INDEX, 'maule').length <= 8);
    assert.ok(buscarComunas(INDEX, 'a').length <= 8);
  });
});

describe('orden de los resultados', () => {
  const index = [
    { code: 1, name: 'Otra', region: 'Talca' },
    { code: 2, name: 'Talca', region: 'Maule' },
    { code: 3, name: 'Talcahuano', region: 'Biobío' },
    { code: 4, name: 'Algo', region: 'Maule' },
  ];
  test('primero el nombre exacto, después el que empieza igual y al final la región', () => {
    assert.deepEqual(nombres(buscarComunas(index, 'talca')), ['Talca', 'Talcahuano', 'Otra']);
  });
  test('no muta el índice recibido', () => {
    const copia = index.map((c) => c.name);
    buscarComunas(index, 'maule');
    assert.deepEqual(nombres(index), copia);
  });
});
