/* Pruebas de web/js/buscador.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buscarComunas, buscarLocalidades, buscarLugares, normalizar } from '../../web/js/buscador.js';

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

describe('buscar localidades (MAPA-167)', () => {
  const localidades = [
    { name: 'Panimávida', comuna: 'Colbún', tipo: 'pueblo', lat: -35.76, lon: -71.42 },
    { name: 'Quinamávida', comuna: 'Colbún', tipo: 'pueblo', lat: -35.81, lon: -71.43 },
    { name: 'Norte Chico', comuna: '', tipo: 'sector', lat: -33.0, lon: -71.0 },
    { name: 'Villa Las Rosas', comuna: 'Los Andes', tipo: 'villa', lat: -32.8, lon: -70.6 },
    { name: 'Puerto Ejemplo', comuna: 'Puerto Montt', tipo: 'ciudad', lat: -41.4, lon: -72.9 },
  ];
  test('encuentra por nombre, con y sin diacríticos', () => {
    assert.equal(buscarLocalidades(localidades, 'panimavida')[0].name, 'Panimávida');
    assert.equal(buscarLocalidades(localidades, 'PANIMÁVIDA')[0].name, 'Panimávida');
  });
  test('encuentra por nombre de la comuna', () => {
    const hits = buscarLocalidades(localidades, 'colbun');
    assert.ok(hits.length >= 2);
    assert.ok(hits.every((l) => l.comuna === 'Colbún'));
  });
  test('una localidad sin comuna se encuentra igual por su nombre', () => {
    assert.equal(buscarLocalidades(localidades, 'norte chico')[0].name, 'Norte Chico');
  });
  test('a empate de coincidencia gana el tipo más alto', () => {
    const idx = [
      { name: 'Sector Algarrobo', comuna: 'X', tipo: 'sector', lat: 0, lon: 0 },
      { name: 'Algarrobo Centro', comuna: 'X', tipo: 'ciudad', lat: 0, lon: 0 },
    ];
    assert.equal(buscarLocalidades(idx, 'algarrobo')[0].tipo, 'ciudad');
  });
  test('texto vacío o sin coincidencias devuelve []', () => {
    assert.deepEqual(buscarLocalidades(localidades, ''), []);
    assert.deepEqual(buscarLocalidades(localidades, 'zzzz'), []);
    assert.deepEqual(buscarLocalidades(null, 'talca'), []);
  });
});

describe('busqueda combinada comunas + localidades (MAPA-167)', () => {
  const comunas = [
    { code: 1, name: 'Colbún', region: 'Maule', center: [-71.4, -35.7], bbox: [-72, -36, -71, -35] },
    { code: 2, name: 'Talca', region: 'Maule', center: [-71.6, -35.4], bbox: [-72, -36, -71, -35] },
  ];
  const localidades = [
    { name: 'Panimávida', comuna: 'Colbún', tipo: 'pueblo', lat: -35.76, lon: -71.42 },
    { name: 'Talcamávida', comuna: 'Pencahue', tipo: 'pueblo', lat: -35.4, lon: -71.8 },
  ];
  test('primero las comunas, después las localidades', () => {
    const hits = buscarLugares(comunas, localidades, 'talca');
    assert.equal(hits[0].kind, 'comuna');
    assert.equal(hits[0].name, 'Talca');
    assert.equal(hits[1].kind, 'localidad');
    assert.equal(hits[1].name, 'Talcamávida');
  });
  test('cada resultado queda marcado con kind', () => {
    const hits = buscarLugares(comunas, localidades, 'panimavida');
    assert.equal(hits[0].kind, 'localidad');
  });
  test('respeta el mismo tope de 8 resultados', () => {
    const muchas = Array.from({ length: 12 }, (_, i) => ({ code: i, name: `San ${i}`, region: 'R', center: [0, 0], bbox: [0, 0, 0, 0] }));
    const locs = [{ name: 'San José Viejo', comuna: 'X', tipo: 'pueblo', lat: 0, lon: 0 }];
    const hits = buscarLugares(muchas, locs, 'san');
    assert.ok(hits.length <= 8);
    assert.ok(hits.every((h) => h.kind === 'comuna'));
  });
  test('si las comunas no llenan el tope, las localidades completan', () => {
    const muchasLocs = Array.from({ length: 12 }, (_, i) => ({ name: `Pueblo ${i}`, comuna: 'X', tipo: 'pueblo', lat: 0, lon: 0 }));
    const hits = buscarLugares(comunas, muchasLocs, 'pueblo');
    assert.equal(hits.length, 8);
    assert.ok(hits.every((h) => h.kind === 'localidad'));
  });
  test('el alias «scl» se aplica también a las localidades', () => {
    const locs = [{ name: 'Barrio Santiago Poniente', comuna: 'X', tipo: 'villa', lat: 0, lon: 0 }];
    const hits = buscarLugares([], locs, 'scl');
    assert.equal(hits[0].name, 'Barrio Santiago Poniente');
  });
  test('texto vacío devuelve [] aunque haya índices', () => {
    assert.deepEqual(buscarLugares(comunas, localidades, ''), []);
    assert.deepEqual(buscarLugares(comunas, localidades, '   '), []);
  });
  test('funciona con el índice real de localidades', () => {
    const REAL = JSON.parse(readFileSync(new URL('../../web/data/localidades.json', import.meta.url), 'utf8'));
    const objetos = REAL.map(([name, comuna, tipo, lat, lon]) => ({ name, comuna, tipo, lat, lon }));
    const hits = buscarLugares(INDEX, objetos, 'panimavida');
    assert.equal(hits[0]?.kind, 'localidad');
    assert.equal(hits[0]?.name, 'Panimávida');
    assert.equal(hits[0]?.comuna, 'Colbún');
  });
});
