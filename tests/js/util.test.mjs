/* Pruebas de web/js/util.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ago, cardinal, circlePolygon, dual, emberSvg, escapeHtml, fmtCompact, fmtDateTime, fmtNum, fmtTime,
  fmtUTC, haversineKm, isothermPaths, minutesSince, parseUTC, pixelKm, pixelSquare, raw, windFrom, windWords,
} from '../../web/js/util.js';

const T0 = new Date('2024-01-15T12:00:00Z').getTime();

describe('escapeHtml', () => {
  test('escapa los cinco caracteres', () => {
    assert.equal(escapeHtml(`<a href="x">&'</a>`), `&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;`);
  });
  test('null, undefined y números', () => {
    assert.equal(escapeHtml(null), '');
    assert.equal(escapeHtml(undefined), '');
    assert.equal(escapeHtml(0), '0');
  });
});

describe('dual', () => {
  test('produce el par plain/tech', () => {
    assert.equal(String(dual('fácil', 'técnico')), '<span class="x-plain">fácil</span><span class="x-tech">técnico</span>');
  });
  test('escapa lo interpolado', () => {
    assert.equal(String(dual('a<b>', 'x&y')), '<span class="x-plain">a&lt;b&gt;</span><span class="x-tech">x&amp;y</span>');
  });
  test('raw() pasa el HTML sin escapar', () => {
    assert.equal(String(dual(raw('<b>a</b>'), 'x')), '<span class="x-plain"><b>a</b></span><span class="x-tech">x</span>');
  });
});

describe('fmtNum / fmtCompact', () => {
  test('enteros con separador de miles es-CL', () => {
    assert.equal(fmtNum(0), '0');
    assert.equal(fmtNum(1234567), '1.234.567');
  });
  test('decimales según digits', () => {
    assert.equal(fmtNum(1.5, 1), '1,5');
    assert.equal(fmtNum(1234.56, 1), '1.234,6');
    assert.equal(fmtNum(1.56), '2');
  });
  test('no finitos → —', () => {
    assert.equal(fmtNum(null), '—');
    assert.equal(fmtNum(NaN), '—');
    assert.equal(fmtNum(Infinity), '—');
    assert.equal(fmtCompact(NaN), '—');
  });
  test('compact con unidad', () => {
    assert.equal(fmtCompact(999), '999');
    assert.equal(fmtCompact(1200), '1,2 K');
    assert.equal(fmtCompact(1234567), '1,2 M');
  });
});

describe('fechas', () => {
  test('parseUTC asume Z si no hay zona', () => {
    assert.equal(parseUTC('2024-01-15T15:30:00').toISOString(), '2024-01-15T15:30:00.000Z');
    assert.equal(parseUTC('2024-01-15T15:30:00Z').toISOString(), '2024-01-15T15:30:00.000Z');
    assert.equal(parseUTC('2024-01-15T15:30:00+03:00').toISOString(), '2024-01-15T12:30:00.000Z');
    assert.ok(Number.isNaN(parseUTC('basura').getTime()));
  });
  test('fmtTime y fmtDateTime en hora de Chile (verano UTC-3, invierno UTC-4)', () => {
    assert.equal(fmtTime('2024-01-15T15:30:00Z'), '12:30');
    assert.equal(fmtTime('2024-07-15T15:30:00Z'), '11:30');
    assert.equal(fmtDateTime('2024-01-15T15:30:00Z'), '15 ene, 12:30');
    assert.equal(fmtUTC('2024-01-15T15:30:00'), '15:30 UTC');
  });
  test('ago con now fijo', () => {
    assert.equal(ago('2024-01-15T11:59:50Z', T0), 'recién');
    assert.equal(ago('2024-01-15T11:48:00Z', T0), 'hace 12 min');
    assert.equal(ago('2024-01-15T08:50:00Z', T0), 'hace 3 h');
    assert.equal(ago('2024-01-13T10:00:00Z', T0), 'hace 2 días');
    assert.equal(ago('2024-01-16T00:00:00Z', T0), 'recién');
    assert.equal(ago(null, T0), 'sin datos');
  });
  test('minutesSince con now fijo', () => {
    assert.equal(minutesSince('2024-01-15T11:30:00Z', T0), 30);
    assert.equal(minutesSince(null, T0), Infinity);
    // Fecha inválida: NaN, no Infinity (comportamiento actual).
    assert.ok(Number.isNaN(minutesSince('basura', T0)));
  });
});

describe('viento', () => {
  test('cardinal cubre los 8 rumbos', () => {
    const rumbos = ['norte', 'noreste', 'este', 'sureste', 'sur', 'suroeste', 'oeste', 'noroeste'];
    rumbos.forEach((r, i) => assert.equal(cardinal(i * 45), r));
  });
  test('cardinal con grados negativos y fuera de rango', () => {
    assert.equal(cardinal(-90), 'oeste');
    assert.equal(cardinal(-45), 'noroeste');
    assert.equal(cardinal(725), 'norte');
    assert.equal(cardinal(359), 'norte');
  });
  test('windFrom y windWords', () => {
    assert.equal(windFrom(180), 'desde el sur');
    assert.equal(windFrom(NaN), '');
    assert.equal(windFrom(undefined), '');
    assert.deepEqual(windWords(0), { from: 'norte', to: 'sur' });
    assert.deepEqual(windWords(90), { from: 'este', to: 'oeste' });
    assert.deepEqual(windWords(200), { from: 'sur', to: 'norte' });
    assert.equal(windWords(NaN), null);
  });
});

describe('geometría', () => {
  test('haversineKm: distancia conocida y simetría', () => {
    const stgo = [-33.45, -70.66];
    const conce = [-36.82, -73.05];
    const d = haversineKm(...stgo, ...conce);
    assert.ok(Math.abs(d - 433.15) < 0.5, `distancia ${d}`);
    assert.equal(d, haversineKm(...conce, ...stgo));
    assert.equal(haversineKm(-33.45, -70.66, -33.45, -70.66), 0);
  });
  test('circlePolygon: anillo cerrado con steps+1 puntos', () => {
    const p = circlePolygon(-70.66, -33.45, 5);
    const ring = p.coordinates[0];
    assert.equal(p.type, 'Polygon');
    assert.equal(ring.length, 65);
    assert.deepEqual(ring[0], ring.at(-1));
    assert.equal(circlePolygon(-70.66, -33.45, 5, 8).coordinates[0].length, 9);
  });
  test('pixelSquare: cuadrado cerrado centrado', () => {
    const p = pixelSquare(-70.66, -33.45, 2);
    const ring = p.coordinates[0];
    assert.equal(p.type, 'Polygon');
    assert.equal(ring.length, 5);
    assert.deepEqual(ring[0], ring.at(-1));
    const lons = ring.slice(0, 4).map((c) => c[0]);
    const lats = ring.slice(0, 4).map((c) => c[1]);
    assert.ok(Math.abs((Math.min(...lons) + Math.max(...lons)) / 2 - -70.66) < 1e-9);
    assert.ok(Math.abs((Math.min(...lats) + Math.max(...lats)) / 2 - -33.45) < 1e-9);
  });
  test('pixelKm por sensor', () => {
    assert.equal(pixelKm({ sensor: 'ABI' }), 2.5);
    assert.equal(pixelKm({ sensor: 'MODIS' }), 1);
    assert.equal(pixelKm({ sensor: 'VIIRS' }), 0.375);
    assert.equal(pixelKm({ sensor: 'OTRO' }), 0.375);
  });
});

describe('isotermas y brasa', () => {
  test('isothermPaths es determinista por seed', () => {
    const a = isothermPaths({ rings: 3, seed: 7 });
    const b = isothermPaths({ rings: 3, seed: 7 });
    const c = isothermPaths({ rings: 3, seed: 8 });
    assert.equal(a.length, 3);
    assert.deepEqual(a, b);
    assert.notDeepEqual(a, c);
    a.forEach((d) => assert.match(d, /^M.+Z$/));
  });
  test('emberSvg devuelve un fragmento SVG con id único', () => {
    const s1 = String(emberSvg({ tone: 'brasa', seed: 7 }));
    const s2 = String(emberSvg({ tone: 'brasa', seed: 7 }));
    assert.match(s1, /^<svg class="ember ember-brasa"/);
    assert.match(s1, /<circle class="core"/);
    assert.notEqual(s1, s2);
  });
});
