/* Pruebas de `coincideBusqueda` de web/js/focos.js con node:test: el filtro de la
 * lista de focos coincide sobre el texto de la fila (comuna, región y nombre del
 * incendio), sin tildes y sin distinción de mayúsculas. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

const { coincideBusqueda } = await import('../../web/js/focos.js');

const FILA = 'En curso según CONAF «QUEIPUL 2» · Victoria, La Araucanía 25 oct 2026, 20:02 — 0,01 ha Ver la ficha';

describe('coincideBusqueda', () => {
  test('consulta vacía o de espacios muestra todo', () => {
    assert.equal(coincideBusqueda(FILA, ''), true);
    assert.equal(coincideBusqueda(FILA, '   '), true);
  });

  test('coincide por comuna', () => {
    assert.equal(coincideBusqueda(FILA, 'victoria'), true);
  });

  test('coincide por región, con o sin tilde', () => {
    assert.equal(coincideBusqueda(FILA, 'araucania'), true);
    assert.equal(coincideBusqueda(FILA, 'Araucanía'), true);
  });

  test('coincide por nombre del incendio, sin importar mayúsculas', () => {
    assert.equal(coincideBusqueda(FILA, 'queipul'), true);
  });

  test('no inventa coincidencias', () => {
    assert.equal(coincideBusqueda(FILA, 'quilpue'), false);
    assert.equal(coincideBusqueda(FILA, 'santiago'), false);
  });
});
