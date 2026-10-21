/* Pruebas de la resolución nombre de comuna → código del índice territorial (CASOS-01). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { codeDeComuna } from '../../web/js/nominados.js';

const INDEX = [
  { code: 7301, name: 'Hualañé', region: 'Maule' },
  { code: 13101, name: 'Ñuñoa', region: 'Metropolitana' },
  { code: 5801, name: 'Quilpué', region: 'Valparaíso' },
];

describe('codeDeComuna', () => {
  test('resuelve el nombre exacto', () => {
    assert.equal(codeDeComuna(INDEX, 'Hualañé'), 7301);
    assert.equal(codeDeComuna(INDEX, 'Ñuñoa'), 13101);
  });
  test('resuelve sin tildes ni ñ', () => {
    assert.equal(codeDeComuna(INDEX, 'hualane'), 7301);
    assert.equal(codeDeComuna(INDEX, 'nunoa'), 13101);
    assert.equal(codeDeComuna(INDEX, 'quilpue'), 5801);
  });
  test('un nombre que no está en el índice no inventa un código', () => {
    assert.equal(codeDeComuna(INDEX, 'Springfield'), null);
    assert.equal(codeDeComuna(INDEX, ''), null);
    assert.equal(codeDeComuna(INDEX, null), null);
  });
  test('sin índice devuelve null', () => {
    assert.equal(codeDeComuna([], 'Hualañé'), null);
    assert.equal(codeDeComuna(null, 'Hualañé'), null);
  });
});
