import test from 'node:test';
import assert from 'node:assert/strict';
import { summaryByPlace } from '../../web/js/alertas-resumen.js';

const a = (place, level = 'aviso', kind = 'oficial', feedback = null) => ({
  place: place === null ? null : { name: place }, level, kind, feedback,
});

test('lista vacía y null no lanzan', () => {
  assert.deepEqual(summaryByPlace([]), []);
  assert.deepEqual(summaryByPlace(null), []);
});

test('agrupa por lugar, ordena por total y luego por nombre', () => {
  const s = summaryByPlace([a('Casa', 'urgente'), a('Parcela'), a('Casa'), a('Parcela'), a('Casa')]);
  assert.equal(s[0].place, 'Casa');
  assert.equal(s[0].total, 3);
  assert.equal(s[0].urgente, 1);
  assert.equal(s[1].place, 'Parcela');
  assert.equal(s[1].total, 2);
  assert.equal(s[1].aviso, 2);
});

test('avisos sin lugar van a place null', () => {
  const s = summaryByPlace([a(null), a('Casa')]);
  assert.equal(s.length, 2);
  const nulo = s.find((x) => x.place === null);
  assert.equal(nulo.total, 1);
});

test('kind y feedback desconocidos cuentan en total pero no en categorías', () => {
  const [x] = summaryByPlace([a('Casa', 'aviso', 'dmc', 'rarito')]);
  assert.equal(x.total, 1);
  assert.deepEqual(x.kinds, { oficial: 0, reporte: 0, diario: 0, prueba: 0 });
  assert.deepEqual(x.feedback, { sirvio: 0, no_sirvio: 0, quema: 0 });
});

test('feedback mixto y ningún contador en undefined', () => {
  const [x] = summaryByPlace([a('Casa', 'aviso', 'oficial', 'sirvio'), a('Casa', 'urgente', 'prueba', 'quema'), a('Casa', 'aviso', 'reporte', 'no_sirvio')]);
  assert.deepEqual(x.feedback, { sirvio: 1, no_sirvio: 1, quema: 1 });
  assert.deepEqual(x.kinds, { oficial: 1, reporte: 1, diario: 0, prueba: 1 });
  for (const v of [x.total, x.urgente, x.aviso, ...Object.values(x.kinds), ...Object.values(x.feedback)]) {
    assert.notEqual(v, undefined);
  }
});
