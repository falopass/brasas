/* Pruebas de web/js/trendview.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { headline, line, tone } from '../../web/js/trendview.js';

const row = (change, current, previous, change_label) =>
  ({ target_date: '2026-10-20', current, previous, change, change_label });

describe('tone', () => {
  test('cada cambio tiene su tono', () => {
    assert.equal(tone('sube'), 'st-riesgo');
    assert.equal(tone('baja'), 'st-tranquilo');
    assert.equal(tone('igual'), '');
    assert.equal(tone('sin_anterior'), 'muted');
    assert.equal(tone('inventado'), '');
  });
});

describe('line', () => {
  test('sube: niveles y etiqueta del servidor', () => {
    assert.equal(
      line(row('sube', 'alto', 'moderado', 'Más alto que el pronóstico de la semana pasada')),
      'moderado → alto · Más alto que el pronóstico de la semana pasada');
  });
  test('baja: niveles y etiqueta del servidor', () => {
    assert.equal(
      line(row('baja', 'bajo', 'alto', 'Más bajo que el pronóstico de la semana pasada')),
      'alto → bajo · Más bajo que el pronóstico de la semana pasada');
  });
  test('igual: un solo nivel, sin flecha consigo mismo', () => {
    assert.equal(
      line(row('igual', 'extremo', 'extremo', 'Igual que el pronóstico de la semana pasada')),
      'extremo · Igual que el pronóstico de la semana pasada');
  });
  test('sin_anterior: no compara, solo avisa', () => {
    assert.equal(
      line(row('sin_anterior', 'alto', null, 'No hay pronóstico de la semana pasada para ese día')),
      'No hay pronóstico de la semana pasada para ese día');
  });
  test('sin etiqueta del servidor usa la frase de respaldo', () => {
    assert.equal(line(row('sin_anterior', 'alto', null)), 'Sin pronóstico de la semana pasada para ese día');
    assert.equal(line(null), '');
  });
});

describe('headline', () => {
  test('resume los cambios y los días sin con qué compararse', () => {
    assert.equal(headline({ sube: 3, baja: 0, igual: 0, sin_anterior: 2 }),
      'Esta semana 3 días suben y 2 no tienen con qué compararse');
  });
  test('une los cuatro conteos con singular y plural', () => {
    assert.equal(headline({ sube: 1, baja: 1, igual: 1, sin_anterior: 1 }),
      'Esta semana 1 día sube, 1 día baja, 1 día sigue igual y 1 no tiene con qué compararse');
    assert.equal(headline({ sube: 0, baja: 2, igual: 4, sin_anterior: 0 }),
      'Esta semana 2 días bajan y 4 días siguen igual');
  });
  test('solo días sin anterior se resume entero', () => {
    assert.equal(headline({ sube: 0, baja: 0, igual: 0, sin_anterior: 7 }),
      'Sin pronóstico de la semana pasada para comparar');
  });
  test('con ceros devuelve vacío', () => {
    assert.equal(headline({ sube: 0, baja: 0, igual: 0, sin_anterior: 0 }), '');
    assert.equal(headline(null), '');
    assert.equal(headline(undefined), '');
  });
});
