/* Contrato de los filtros de la Historia (web/js/nominados.js): comuna, temporada y hectáreas.
 * casos.test.mjs los ejercita desde la vista; aquí se fijan los bordes que nadie más cubre. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { filterNominados, foldComuna, sumHa } from '../../web/js/nominados.js';

const ITEMS = [
  { name: 'SIN HA', comuna: 'Talca', season: '2016-2017' },
  { name: 'TALCA UNO', comuna: 'Talca', season: '2023-2024', ha: 120 },
  { name: 'TALCA DOS', comuna: 'Talca', season: '2016-2017', ha: 40 },
  { name: 'SAN CLEMENTE', comuna: 'San Clemente', season: '2023-2024', ha: 900 },
  { name: 'CHILLAN', comuna: 'Chillán', season: '2016-2017', ha: 200 },
  { name: 'NUBLE', comuna: 'Ñuble', season: '2016-2017', ha: 60 },
];

const names = (rows) => rows.map((i) => i.name);

describe('foldComuna', () => {
  test('quita tildes y «ñ», recorta y colapsa espacios', () => {
    assert.equal(foldComuna(' Ñuñoa '), 'nunoa');
    assert.equal(foldComuna('LOS  ÁNGELES'), 'los angeles');
    assert.equal(foldComuna('NUNOA'), 'nunoa');
  });
  test('sin texto devuelve cadena vacía', () => {
    assert.equal(foldComuna(null), '');
    assert.equal(foldComuna(undefined), '');
  });
});

describe('filterNominados', () => {
  test('«talca» encuentra Talca y no San Clemente', () => {
    assert.deepEqual(names(filterNominados(ITEMS, { comuna: 'talca' })), ['TALCA UNO', 'TALCA DOS', 'SIN HA']);
  });
  test('«nuble» encuentra la comuna «Ñuble» (la ñ se pliega a n)', () => {
    assert.deepEqual(names(filterNominados(ITEMS, { comuna: 'nuble' })), ['NUBLE']);
  });
  test('sin filtros devuelve todo, de mayor a menor superficie', () => {
    assert.deepEqual(names(filterNominados(ITEMS, {})), ['SAN CLEMENTE', 'CHILLAN', 'TALCA UNO', 'NUBLE', 'TALCA DOS', 'SIN HA']);
  });
  // Regla deliberada: la temporada se compara como cadena exacta. «2024» no es «2023-2024».
  test('la temporada coincide exacta y «2024» no calza con «2023-2024»', () => {
    assert.deepEqual(names(filterNominados(ITEMS, { season: '2023-2024' })), ['SAN CLEMENTE', 'TALCA UNO']);
    assert.deepEqual(filterNominados(ITEMS, { season: '2024' }), []);
  });
  test('no muta la lista de entrada', () => {
    const antes = JSON.stringify(ITEMS);
    filterNominados(ITEMS, { comuna: 'talca', season: '2016-2017' });
    filterNominados(ITEMS, {});
    assert.equal(JSON.stringify(ITEMS), antes);
  });
});

describe('sumHa', () => {
  test('un ítem sin ha cuenta como 0 y no rompe el orden', () => {
    const rows = filterNominados(ITEMS, { comuna: 'talca' });
    assert.equal(sumHa(rows), 160);
    assert.equal(sumHa([]), 0);
  });
});
