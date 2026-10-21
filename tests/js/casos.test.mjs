/* Pruebas del filtro de incendios nominados (web/js/nominados.js) y del catálogo de la vista
 * Historia (web/js/views/casos.js): filtros por región, hash y cercanía, sin navegador.
 * casos.js importa ui.js, que registra un listener «online» al cargar: se usa un stub. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { filterNominados, foldComuna, sumHa } from '../../web/js/nominados.js';

globalThis.window = { addEventListener() {} };
const { filaNominado, filtrarPorRegion, ordenarPorCercania, regionesDe, regionFromHash, tarjetaHtml } = await import('../../web/js/views/casos.js');
const CASES = JSON.parse(readFileSync(fileURLToPath(new URL('../../web/data/cases.json', import.meta.url)), 'utf8')).cases;

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

describe('regionesDe', () => {
  test('devuelve las regiones únicas, separando los casos con varias', () => {
    assert.deepEqual(regionesDe(CASES), ['Biobío', 'Valparaíso', 'Ñuble', 'La Araucanía', 'Maule', 'Magallanes']);
  });
});

describe('filtrarPorRegion', () => {
  test('«Maule» devuelve solo Las Máquinas 2017', () => {
    assert.deepEqual(filtrarPorRegion(CASES, 'Maule').map((c) => c.id), ['las-maquinas-2017']);
  });
  test('«Todas» y vacío devuelven los seis casos', () => {
    assert.equal(filtrarPorRegion(CASES, 'Todas').length, 6);
    assert.equal(filtrarPorRegion(CASES, '').length, 6);
  });
  test('una región compartida trae todos los casos que la incluyen', () => {
    assert.deepEqual(filtrarPorRegion(CASES, 'Biobío').map((c) => c.id), ['penco-lirquen-2026', 'nuble-biobio-araucania-2023']);
  });
});

describe('regionFromHash', () => {
  test('lee la región del hash y devuelve «» cuando no viene', () => {
    assert.equal(regionFromHash('#/casos?region=Maule'), 'Maule');
    assert.equal(regionFromHash('#/casos'), '');
    assert.equal(regionFromHash('#/casos/las-maquinas-2017'), '');
  });
  test('decodifica regiones con espacios y tildes', () => {
    assert.equal(regionFromHash(`#/casos?region=${encodeURIComponent('La Araucanía')}`), 'La Araucanía');
  });
});

describe('ordenarPorCercania', () => {
  test('pone primero el caso más cercano al lugar guardado', () => {
    const curico = { lat: -34.98, lon: -71.24 }; // Curicó, Maule
    assert.equal(ordenarPorCercania(CASES, curico)[0].id, 'las-maquinas-2017');
  });
  test('sin lugar mantiene el orden del archivo', () => {
    assert.deepEqual(ordenarPorCercania(CASES, null).map((c) => c.id), CASES.map((c) => c.id));
    assert.deepEqual(ordenarPorCercania(CASES, { lat: 'x' }).map((c) => c.id), CASES.map((c) => c.id));
  });
});

describe('tarjetaHtml', () => {
  test('la tarjeta es un enlace real a la vista del caso', () => {
    const t = String(tarjetaHtml(CASES.find((c) => c.id === 'las-maquinas-2017')));
    assert.match(t, /^<a\b/);
    assert.match(t, /href="#\/casos\/las-maquinas-2017"/);
    assert.doesNotMatch(t, /tabindex=|role=/);
  });
  test('con distancia marca «a N km de tu lugar»', () => {
    const t = String(tarjetaHtml(CASES[0], 60));
    assert.match(t, /a 60 km de tu lugar/);
  });
});

const INDEX = [
  { code: 7301, name: 'Hualañé', region: 'Maule' },
  { code: 13101, name: 'Ñuñoa', region: 'Metropolitana' },
];

describe('filaNominado', () => {
  test('una comuna conocida enlaza a la ficha de riesgo', () => {
    const t = String(filaNominado({ name: 'El fuego', comuna: 'Hualañé', ha: 12.5, season: '2024-2025' }, INDEX));
    assert.match(t, /href="#\/riesgo\?comuna=7301"/);
    assert.match(t, /aria-label="Ver el riesgo de Hualañé"/);
    assert.match(t, /12,5 ha/);
  });
  test('una comuna desconocida queda como texto plano', () => {
    const t = String(filaNominado({ name: 'El fuego', comuna: 'Springfield', ha: 1, season: '2024-2025' }, INDEX));
    assert.doesNotMatch(t, /href="#\/riesgo/);
    assert.match(t, /Springfield/);
  });
});
