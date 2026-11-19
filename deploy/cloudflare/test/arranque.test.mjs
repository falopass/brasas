import { test } from 'node:test';
import assert from 'node:assert/strict';
import { esFalloDeArranqueDelContenedor } from '../src/arranque.ts';

test('reconoce los 500 de arranque del contenedor', () => {
  for (const body of [
    'container is not running',
    'Failed to start container: the container is not listening',
    'Container suddenly disconnected, try again',
    'Error proxying request to container: connect ECONNREFUSED',
  ]) {
    assert.equal(esFalloDeArranqueDelContenedor(body), true, body);
  }
});

test('no confunde un 500 de la app con arranque', () => {
  for (const body of ['Internal Server Error', '{"detail":"Error inesperado"}', 'container exploded']) {
    assert.equal(esFalloDeArranqueDelContenedor(body), false, body);
  }
});
