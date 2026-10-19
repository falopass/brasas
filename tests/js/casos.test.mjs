/* Pruebas del filtro de incendios nominados (web/js/nominados.js), sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { filterNominados, foldComuna, sumHa } from '../../web/js/nominados.js';

const ITEMS = [
  { name: 'UNO', comuna: 'Ñiquén', season: '2016-2017', ha: 100 },
  { name: 'DOS', comuna: 'Ñiquén', season: '2023-2024', ha: 50 },
  { name: 'TRES', comuna: 'Chillán', season: '2016-2017', ha: 200.5 },
  { name: 'CUATRO', comuna: 'Chillán Viejo', season: '2016-2017', ha: 75 },
  { name: 'CINCO', comuna: 'Quirihue', season: '2016-2017', ha: 300 },
];

describe('foldComuna', () => {
  test('minúsculas, sin tildes y «ñ» pasa a «n»', () => {
    assert.equal(foldComuna('  Ñuble  '), 'nuble');
    assert.equal(foldComuna('Quilpué'), 'quilpue');
    assert.equal(foldComuna('RÍO   IBÁÑEZ'), 'rio ibanez');
  });
  test('vacío y nulos', () => {
    assert.equal(foldComuna(''), '');
    assert.equal(foldComuna(null), '');
    assert.equal(foldComuna(undefined), '');
  });
});

describe('filterNominados', () => {
  test('comuna exacta', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'Quirihue' }).map((i) => i.name), ['CINCO']);
  });
  test('sin tildes ni ñ encuentra la comuna con ellas', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'niquen' }).map((i) => i.name), ['UNO', 'DOS']);
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'Chillan Viejo' }).map((i) => i.name), ['CUATRO']);
  });
  test('el texto libre calza por prefijo («chillan» trae Chillán y Chillán Viejo)', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'chillan' }).map((i) => i.name), ['TRES', 'CUATRO']);
  });
  test('sin resultados', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'Springfield' }), []);
  });
  test('se combina con la temporada', () => {
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'niquen', season: '2016-2017' }).map((i) => i.name), ['UNO']);
    assert.deepEqual(filterNominados(ITEMS, { comuna: 'niquen', season: '2020-2021' }), []);
  });
  test('solo temporada, como antes', () => {
    assert.equal(filterNominados(ITEMS, { season: '2023-2024' }).length, 1);
    assert.equal(filterNominados(ITEMS, { season: '2016-2017' }).length, 4);
    assert.equal(filterNominados(ITEMS, {}).length, 5);
  });
  test('ordena de mayor a menor superficie', () => {
    assert.deepEqual(filterNominados(ITEMS, { season: '2016-2017' }).map((i) => i.ha), [300, 200.5, 100, 75]);
  });
});

describe('sumHa', () => {
  test('suma las hectáreas del filtro actual', () => {
    assert.equal(sumHa(filterNominados(ITEMS, { season: '2016-2017' })), 675.5);
    assert.equal(sumHa(filterNominados(ITEMS, { comuna: 'niquen' })), 150);
    assert.equal(sumHa([]), 0);
  });
});
