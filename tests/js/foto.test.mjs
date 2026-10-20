/* Pruebas de web/js/foto.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { fitDimensions, shouldShrink } from '../../web/js/foto.js';

describe('fitDimensions', () => {
  test('4032×3024 baja a 1600×1200 manteniendo la proporción', () => {
    assert.deepEqual(fitDimensions(4032, 3024), { width: 1600, height: 1200 });
  });
  test('una foto chica no se amplía', () => {
    assert.deepEqual(fitDimensions(800, 600), { width: 800, height: 600 });
    assert.deepEqual(fitDimensions(1600, 1600), { width: 1600, height: 1600 });
  });
  test('acota por el lado mayor, alto o ancho', () => {
    assert.deepEqual(fitDimensions(3024, 4032), { width: 1200, height: 1600 });
    assert.deepEqual(fitDimensions(3200, 1600), { width: 1600, height: 800 });
  });
  test('dimensiones inválidas devuelven null', () => {
    assert.equal(fitDimensions(0, 0), null);
    assert.equal(fitDimensions(NaN, 600), null);
    assert.equal(fitDimensions(800, -1), null);
    assert.equal(fitDimensions(800, 600, 0), null);
  });
});

describe('shouldShrink', () => {
  test('una imagen de 200 KB ya es liviana', () => {
    assert.equal(shouldShrink({ size: 200_000, type: 'image/jpeg' }), false);
  });
  test('una imagen de 6 MB conviene reducirla', () => {
    assert.equal(shouldShrink({ size: 6_000_000, type: 'image/png' }), true);
    assert.equal(shouldShrink({ size: 6_000_000, type: 'image/heic' }), true);
  });
  test('un PDF no es imagen', () => {
    assert.equal(shouldShrink({ size: 6_000_000, type: 'application/pdf' }), false);
  });
  test('sin type o sin size no se toca', () => {
    assert.equal(shouldShrink({ size: 6_000_000, type: '' }), false);
    assert.equal(shouldShrink(null), false);
    assert.equal(shouldShrink({ size: NaN, type: 'image/jpeg' }), false);
  });
});
