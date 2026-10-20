/* Pruebas de web/js/foto.js con node:test: dimensiones de salida y decisión de reducir. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { fitDimensions, shouldShrink } from '../../web/js/foto.js';

describe('fitDimensions', () => {
  test('reduce al lado mayor conservando la proporción', () => {
    assert.deepEqual(fitDimensions(4032, 3024), { width: 1600, height: 1200 });
  });
  test('nunca amplía una foto ya pequeña', () => {
    assert.deepEqual(fitDimensions(800, 600), { width: 800, height: 600 });
  });
  test('dimensiones inválidas devuelven null', () => {
    for (const [w, h] of [[0, 0], [-5, 100], [Number.NaN, 10], [100, Number.NaN]]) {
      assert.equal(fitDimensions(w, h), null, `${w}x${h}`);
    }
  });
});

describe('shouldShrink', () => {
  test('una imagen pequeña se envía tal cual', () => {
    assert.equal(shouldShrink({ size: 200 * 1024, type: 'image/jpeg' }), false);
  });
  test('una imagen de varios MB se reduce', () => {
    assert.equal(shouldShrink({ size: 6 * 1024 * 1024, type: 'image/jpeg' }), true);
  });
  test('un archivo que no es imagen nunca se procesa', () => {
    assert.equal(shouldShrink({ size: 6 * 1024 * 1024, type: 'application/pdf' }), false);
  });
});
