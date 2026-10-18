// Prueba de la retención de 24 h de las copias diarias (OPS privacidad). Corre con
// `node --test` directo sobre el TS: el módulo solo usa sintaxis de tipos borrable.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { copiasVencidas, RETENCION_MS } from '../src/retention.ts';

const NOW = Date.UTC(2026, 9, 18, 12, 0, 0);
const obj = (key, ageMs) => ({ key, uploaded: new Date(NOW - ageMs) });

test('borra solo las copias diarias con más de 24 horas', () => {
  const objetos = [
    obj('db/diario/2026-10-16.db', RETENCION_MS + 600_000), // 24 h + 10 min → borra
    obj('db/diario/2026-10-17.db', 60 * 60 * 1000),         // 1 h → conserva
    obj('db/diario/2026-10-18.db', 5 * 60 * 1000),          // 5 min → conserva
    obj('db/brasa.db', RETENCION_MS + 86_400_000),          // no es copia diaria → nunca
    obj('photos/a1.jpg', RETENCION_MS + 86_400_000),        // foto → nunca
  ];
  assert.deepEqual(copiasVencidas(objetos, NOW), ['db/diario/2026-10-16.db']);
});

test('justo en las 24 horas todavía se conserva', () => {
  assert.deepEqual(copiasVencidas([obj('db/diario/2026-10-17.db', RETENCION_MS)], NOW), []);
});
