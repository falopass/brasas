/* Pruebas de summarizePanel (web/js/charts.js) con node:test, sin navegador ni DOM. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { segmentos, summarizePanel } from '../../web/js/charts.js';

// Horas UTC de un día de enero: Chile está en UTC-3, así que 16:00Z se lee «13:00».
const TIMES = ['2024-01-15T15:00:00Z', '2024-01-15T16:00:00Z', '2024-01-15T17:00:00Z', '2024-01-15T18:00:00Z'];

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

// Escalas de juguete: x e y nunca coinciden, así una coordenada no se confunde con otra.
const X = (i) => 40 + i * 10;
const Y = (v) => 100 - v;

describe('segmentos', () => {
  test('serie continua: un tramo, línea y área del mismo tramo', () => {
    const [seg] = segmentos([1, 2, 3], X, Y);
    assert.equal(seg.d, `M${X(0)},${Y(1)}L${X(1)},${Y(2)}L${X(2)},${Y(3)}`);
    assert.equal(seg.areaD, `M${X(0)},${Y(0)}L${X(0)},${Y(1)}L${X(1)},${Y(2)}L${X(2)},${Y(3)}L${X(2)},${Y(0)}Z`);
    assert.equal(seg.firstX, X(0));
    assert.equal(seg.lastX, X(2));
  });
  test('hueco al medio: dos tramos y el área no cruza el vacío', () => {
    const segs = segmentos([1, null, 2, 3], X, Y);
    assert.equal(segs.length, 2);
    assert.deepEqual([segs[0].firstX, segs[0].lastX], [X(0), X(0)]);
    assert.deepEqual([segs[1].firstX, segs[1].lastX], [X(2), X(3)]);
    // Ningún área pisa la x del hueco.
    for (const s of segs) assert.ok(!s.areaD.includes(String(X(1))), s.areaD);
  });
  test('hueco al principio y al final: un solo tramo, sin fantasmas', () => {
    const segs = segmentos([null, 5, 6, null], X, Y);
    assert.equal(segs.length, 1);
    assert.deepEqual([segs[0].firstX, segs[0].lastX], [X(1), X(2)]);
  });
  test('serie entera nula: ningún path', () => {
    assert.deepEqual(segmentos([null, undefined, NaN], X, Y), []);
  });
  test('un solo punto: la línea se dibuja como punto y no hay área', () => {
    const [seg] = segmentos([null, 7, null], X, Y);
    assert.equal(seg.d, `M${X(1)},${Y(7)}L${X(1)},${Y(7)}`);
    assert.equal(seg.areaD, '');
  });
});
