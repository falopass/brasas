// Prueba del tope del registro de revalidaciones: pasadas las 500 entradas expulsa la más vieja.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { recuerdaIntento, REINTENTOS_MAX } from '../src/reintentos.ts';

test('al superar el tope expulsa la entrada más vieja', () => {
  const map = new Map();
  for (let i = 0; i < REINTENTOS_MAX; i++) recuerdaIntento(map, `https://x/api/status?i=${i}`, i);
  assert.equal(map.size, REINTENTOS_MAX);
  recuerdaIntento(map, 'https://x/api/status?nuevo=1', REINTENTOS_MAX + 1);
  assert.equal(map.size, REINTENTOS_MAX, 'el registro no pasa del tope');
  assert.ok(map.has('https://x/api/status?nuevo=1'));
  assert.ok(!map.has('https://x/api/status?i=0'), 'la más vieja sale primero');
  assert.ok(map.has('https://x/api/status?i=1'), 'la siguiente queda');
});

test('una clave existente se actualiza sin expulsar a nadie', () => {
  const map = new Map();
  for (let i = 0; i < REINTENTOS_MAX; i++) recuerdaIntento(map, `k${i}`, i);
  recuerdaIntento(map, 'k0', 9999);
  assert.equal(map.size, REINTENTOS_MAX);
  assert.equal(map.get('k0'), 9999);
  assert.ok(map.has(`k${REINTENTOS_MAX - 1}`));
});
