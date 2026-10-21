/* Pruebas de web/js/formato.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { ago, fmtDateTime, fmtNum, fmtTime, parseUTC, TZ } from '../../web/js/formato.js';

const NOW = new Date('2026-01-15T12:00:00Z').getTime();

describe('hora de Chile', () => {
  test('verano (enero): UTC-3', () => {
    const out = fmtDateTime('2026-01-15T02:30:00Z');
    assert.match(out, /14/);
    assert.match(out, /ene/);
    assert.match(out, /23:30/);
  });
  test('invierno (julio): UTC-4', () => {
    const out = fmtDateTime('2026-07-15T02:30:00Z');
    assert.match(out, /14/);
    assert.match(out, /jul/);
    assert.match(out, /22:30/);
  });
  test('fmtTime y formato largo de respuesta', () => {
    assert.equal(fmtTime('2026-01-15T02:30:00Z'), '23:30');
    const largo = fmtDateTime('2026-01-15T02:30:00Z', { month: 'long', year: 'numeric' });
    assert.match(largo, /enero/);
    assert.match(largo, /2026/);
    assert.match(largo, /23:30/);
  });
  test('fecha ilegible → sin datos / —', () => {
    assert.equal(fmtDateTime('no es fecha'), 'sin datos');
    assert.equal(fmtTime(null), '—');
  });
});

describe('ago', () => {
  test('minutos, horas y días con now fijo', () => {
    assert.equal(ago('2026-01-15T11:48:00Z', NOW), 'hace 12 min');
    assert.equal(ago('2026-01-15T09:00:00Z', NOW), 'hace 3 h');
    assert.equal(ago('2026-01-13T11:00:00Z', NOW), 'hace 2 días');
  });
  test('bordes: recién y sin datos', () => {
    assert.equal(ago('2026-01-15T11:59:40Z', NOW), 'recién');
    assert.equal(ago('', NOW), 'sin datos');
  });
  test('la edad mostrada nunca adelanta la real (unidades completas)', () => {
    // 90 segundos son 1 min completo, no «hace 2 min»
    assert.equal(ago('2026-01-15T11:58:30Z', NOW), 'hace 1 min');
    // cortes de minutos → horas
    assert.equal(ago('2026-01-15T11:01:00Z', NOW), 'hace 59 min'); // 59 min
    assert.equal(ago('2026-01-15T11:00:00Z', NOW), 'hace 1 h'); // 60 min
    assert.equal(ago('2026-01-15T10:31:00Z', NOW), 'hace 1 h'); // 89 min
    assert.equal(ago('2026-01-15T10:30:00Z', NOW), 'hace 1 h'); // 90 min
    assert.equal(ago('2026-01-15T10:01:00Z', NOW), 'hace 1 h'); // 119 min, antes «hace 2 h»
    // cortes de horas → días
    assert.equal(ago('2026-01-14T12:10:00Z', NOW), 'hace 23 h'); // 23 h 50 min
    assert.equal(ago('2026-01-14T11:00:00Z', NOW), 'hace 25 h'); // 25 h
    assert.equal(ago('2026-01-13T12:01:00Z', NOW), 'hace 47 h'); // 47 h 59 min, antes «hace 2 días»
    assert.equal(ago('2026-01-13T12:00:00Z', NOW), 'hace 2 días'); // 48 h justo
  });
});

describe('fmtNum y parseUTC', () => {
  test('formato chileno', () => {
    assert.equal(fmtNum(1234.5, 1), '1.234,5');
    assert.equal(fmtNum(NaN), '—');
  });
  test('desfases con signo menos se respetan', () => {
    assert.equal(parseUTC('2026-01-15T15:30:00-03:00').toISOString(), '2026-01-15T18:30:00.000Z');
  });
  test('TZ exportado', () => {
    assert.equal(TZ, 'America/Santiago');
  });
});
