/* Pruebas de web/js/charts.js: aritmética de ejes y cursor, y summarizePanel, sin navegador. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { indexFromX, niceMax, summarizePanel } from '../../web/js/charts.js';

// Horas UTC de un día de enero: Chile está en UTC-3, así que 16:00Z se lee «13:00».
const TIMES = ['2024-01-15T15:00:00Z', '2024-01-15T16:00:00Z', '2024-01-15T17:00:00Z', '2024-01-15T18:00:00Z'];

describe('niceMax', () => {
  test('valores no positivos o no finitos dan 1', () => {
    assert.equal(niceMax(0), 1);
    assert.equal(niceMax(NaN), 1);
    assert.equal(niceMax(-5), 1);
  });
  test('redondea al siguiente paso "bonito"', () => {
    assert.equal(niceMax(7), 8);
    assert.equal(niceMax(950), 1000);
    assert.equal(niceMax(1), 1);
  });
  test('es monótona en valores positivos: a <= b implica niceMax(a) <= niceMax(b)', () => {
    // 0 queda fuera a propósito: niceMax(0) = 1 por el piso de los no positivos,
    // mientras niceMax(0,3) = 0,3; la monotonía solo se exige con entradas > 0.
    const muestra = [0.3, 1, 2.7, 19, 121, 4800];
    for (let i = 0; i < muestra.length; i++) {
      for (let j = i; j < muestra.length; j++) {
        assert.ok(niceMax(muestra[i]) <= niceMax(muestra[j]), `${muestra[i]} <= ${muestra[j]}`);
      }
    }
  });
});

describe('indexFromX', () => {
  test('antes del inicio da 0 y después del final da count-1', () => {
    assert.equal(indexFromX(-50, 0, 100, 5), 0);
    assert.equal(indexFromX(150, 0, 100, 5), 4);
  });
  test('el centro con count par e impar', () => {
    assert.equal(indexFromX(50, 0, 100, 4), 2);
    assert.equal(indexFromX(50, 0, 100, 3), 1);
  });
  test('count = 1 siempre da 0', () => {
    assert.equal(indexFromX(50, 0, 100, 1), 0);
  });
  test('plotWidth = 0 da 0', () => {
    assert.equal(indexFromX(50, 0, 0, 5), 0);
  });
});

describe('summarizePanel', () => {
  test('serie vacía → «sin datos»', () => {
    const panel = { title: 'Viento', unit: 'km/h', series: [{ key: 'w', label: 'Viento', values: [] }] };
    assert.match(summarizePanel(panel, TIMES), /sin datos/);
  });
  test('serie sin valores finitos → «sin datos»', () => {
    const panel = { title: 'Viento', series: [{ key: 'w', values: [null, undefined, NaN] }] };
    assert.match(summarizePanel(panel, TIMES), /sin datos/);
  });
  test('nombra el máximo, el mínimo y la hora del máximo', () => {
    const panel = { title: 'Viento', unit: 'km/h', series: [{ key: 'w', values: [10, 42, 20, 5] }] };
    const s = summarizePanel(panel, TIMES);
    assert.match(s, /máximo 42 km\/h a las 13:00/);
    assert.match(s, /mínimo 5 km\/h/);
    assert.match(s, /^Viento:/);
  });
  test('respeta el umbral del panel', () => {
    const panel = { title: 'Viento', unit: 'km/h', series: [{ key: 'w', values: [10, 42] }],
      threshold: { value: 30, label: '30 km/h', direction: 'above' } };
    assert.match(summarizePanel(panel, TIMES), /Umbral en 30 km\/h/);
  });
  test('umbral sin label usa el valor y la unidad', () => {
    const panel = { title: 'Calor', unit: '°C', series: [{ key: 't', values: [20, 31] }],
      threshold: { value: 30, direction: 'above' } };
    assert.match(summarizePanel(panel, TIMES), /Umbral en 30 °C/);
  });
  test('respeta unit distinto de km/h', () => {
    const panel = { title: 'Zona con calor', unit: 'ha', kind: 'line', series: [{ key: 'cov', values: [100, 300] }] };
    assert.match(summarizePanel(panel, TIMES), /300 ha/);
  });
  test('en barras el máximo es la suma apilada de las series', () => {
    const panel = { title: 'Puntos de calor', kind: 'bars', series: [
      { key: 'a', values: [1, 2] }, { key: 'b', values: [3, 4] },
    ] };
    const s = summarizePanel(panel, TIMES);
    assert.match(s, /máximo 6 a las 13:00/);
    assert.match(s, /mínimo 4/);
  });
  test('en períodos largos nombra el día del máximo', () => {
    const times = ['2024-01-15T15:00:00Z', '2024-01-16T15:00:00Z', '2024-01-17T15:00:00Z'];
    const panel = { title: 'Calor', unit: '°C', series: [{ key: 't', values: [20, 35, 25] }] };
    assert.match(summarizePanel(panel, times), /el 16 ene a las 12:00/);
  });
});
