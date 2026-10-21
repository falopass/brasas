/* Pruebas de las funciones puras de frescura de la página de datos abiertos (DATOS-01). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { edadEnPalabras, filasDeFrescura } from '../../web/js/datos.js';

describe('edadEnPalabras', () => {
  test('411 segundos son 7 minutos', () => {
    assert.equal(edadEnPalabras(411), 'hace 7 minutos');
  });
  test('cero es recién', () => {
    assert.equal(edadEnPalabras(0), 'recién');
  });
  test('7200 segundos son 2 horas', () => {
    assert.equal(edadEnPalabras(7200), 'hace 2 horas');
  });
  test('un día se dice en singular', () => {
    assert.equal(edadEnPalabras(86400), 'hace 1 día');
  });
  test('sin dato no inventa una edad', () => {
    assert.equal(edadEnPalabras(null), 'sin dato');
    assert.equal(edadEnPalabras(undefined), 'sin dato');
    assert.equal(edadEnPalabras('ayer'), 'sin dato');
  });
});

describe('filasDeFrescura', () => {
  const AHORA = Date.parse('2026-10-21T00:00:00Z');
  const status = {
    newest_observation: {
      GOES19_FDCF: '2026-10-20T23:50:00Z',
      VIIRS_NOAA20_NRT: '2026-10-20T22:00:00Z',
      VIIRS_NOAA21_NRT: '2026-10-20T21:00:00Z',
    },
  };

  test('devuelve una fila por fuente con nombre legible y edad', () => {
    const filas = filasDeFrescura(status, AHORA);
    assert.deepEqual(filas.map((f) => f.label), ['GOES-19', 'VIIRS NOAA-20', 'VIIRS NOAA-21']);
    assert.deepEqual(filas.map((f) => f.edad), ['hace 10 minutos', 'hace 2 horas', 'hace 3 horas']);
  });
  test('sin observaciones devuelve lista vacía sin lanzar', () => {
    assert.deepEqual(filasDeFrescura({}, AHORA), []);
    assert.deepEqual(filasDeFrescura(undefined, AHORA), []);
  });
});
