/* Pruebas de summarizePanel (web/js/charts.js) con node:test, sin navegador ni DOM. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { chartCsv, hbar, segmentos, summarizePanel } from '../../web/js/charts.js';

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

describe('chartCsv (DAT-06)', () => {
  const spec = {
    times: ['2024-01-15T15:00:00Z', '2024-01-15T16:00:00Z', '2024-01-15T17:00:00Z'],
    panels: [{ series: [{ key: 'g', label: 'GOES', values: [10, null, 30] }, { key: 'v', label: 'VIIRS/MODIS', values: [5, 1234.5, 7] }] }],
  };
  test('cabecera con hora y una columna por serie; una línea por instante', () => {
    const csv = chartCsv(spec);
    const lineas = csv.slice(1).split('\r\n'); // salta el BOM
    assert.equal(lineas[0], 'hora;GOES;VIIRS/MODIS');
    assert.equal(lineas.length, 4);
    assert.equal(lineas[1], '2024-01-15T15:00:00.000Z;10;5');
  });
  test('null sale como celda vacía, nunca NaN', () => {
    const csv = chartCsv(spec);
    assert.match(csv, /;30/);
    assert.match(csv.split('\r\n')[2], /;;/);
    assert.doesNotMatch(csv, /NaN|null|undefined/);
  });
  test('times vacío → solo cabecera', () => {
    assert.equal(chartCsv({ ...spec, times: [] }).slice(1), 'hora;GOES;VIIRS/MODIS');
  });
  test('empieza con BOM y números con punto decimal sin separador de miles', () => {
    const csv = chartCsv(spec);
    assert.equal(csv.charCodeAt(0), 0xFEFF);
    assert.match(csv, /;1234.5/);
    assert.doesNotMatch(csv, /1\.234,5|1,234\.5/);
  });
});

describe('hbar (barras en SVG, sin estilos en línea)', () => {
  const anchos = (out) => [...String(out).matchAll(/<rect class="([^"]*)" x="([\d.]+)" width="([\d.]+)"/g)].map((m) => [m[1], Number(m[2]), Number(m[3])]);
  test('los tramos se reparten el ancho en proporción y los vacíos no se dibujan', () => {
    const r = anchos(hbar([{ n: 1, cls: 'a' }, { n: 0, cls: 'b' }, { n: 3, cls: 'c' }]));
    assert.deepEqual(r.map((x) => x[0]), ['a', 'c']);
    assert.equal(r[0][1], 0);
    assert.equal(r[1][1], 25);
    assert.ok(Math.abs(r[1][2] - 75) < 1);
  });
  test('con total es un medidor: llega hasta n/total, no pasa del 100 % y dibuja la marca del umbral', () => {
    assert.equal(anchos(hbar([{ n: 23 }], { total: 46, mark: 50 }))[0][2], 50);
    assert.equal(anchos(hbar([{ n: 99 }], { total: 45 }))[0][2], 100);
    assert.match(String(hbar([{ n: 23 }], { total: 46, mark: 50 })), /class="hbar-marca" x="49\.40"/);
  });
  test('sin nada que medir no hay barra; un valor nulo deja solo la pista', () => {
    assert.equal(hbar([{ n: 0 }, { n: null }]), '');
    assert.equal(anchos(hbar([{ n: null }], { total: 45 })).length, 0);
    assert.doesNotMatch(String(hbar([{ n: 5 }], { total: 10 })), /style=/);
  });
});
