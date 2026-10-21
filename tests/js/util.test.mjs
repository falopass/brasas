/* Pruebas de web/js/util.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ago, botonRojoIcs, cardinal, circlePolygon, dual, emberSvg, escapeHtml, fmtCompact, fmtDateTime, fmtNum, fmtTime,
  fmtUTC, haversineKm, isothermPaths, minutesSince, nearestPlacesText, parseUTC, pixelKm, pixelSquare, raw, windFrom, windWords,
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
    assert.equal(parseUTC('2026-10-19T10:00:00-03:00').toISOString(), '2026-10-19T13:00:00.000Z');
    assert.ok(Number.isNaN(parseUTC('basura').getTime()));
    assert.ok(Number.isNaN(parseUTC('').getTime()));
    assert.ok(Number.isNaN(parseUTC(undefined).getTime()));
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
    assert.equal(ago('basura', T0), 'sin datos');
  });
  test('minutesSince con now fijo', () => {
    assert.equal(minutesSince('2024-01-15T11:30:00Z', T0), 30);
    assert.equal(minutesSince(null, T0), Infinity);
    assert.equal(minutesSince('basura', T0), Infinity);
  });
  test('una fecha ilegible no llega a la pantalla y no lanza', () => {
    for (const rota of ['basura', '', undefined, null]) {
      assert.equal(ago(rota, T0), 'sin datos');
      assert.equal(fmtDateTime(rota), 'sin datos');
      assert.equal(fmtTime(rota), '—');
      assert.equal(fmtUTC(rota), '—');
      assert.equal(minutesSince(rota, T0), Infinity);
    }
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

describe('botonRojoIcs', () => {
  const days = [
    { date: '2026-02-10', boton_rojo_hours: '12:00-18:00' },
    { date: '2026-02-11', boton_rojo_hours: null },
    { date: '2026-02-12', boton_rojo_hours: '13:00-17:00' },
  ];
  test('cabecera, cierre y CRLF', () => {
    const ics = botonRojoIcs({ comuna: 'Curicó', days });
    assert.match(ics, /^BEGIN:VCALENDAR\r\n/);
    assert.match(ics, /VERSION:2\.0\r\n/);
    assert.match(ics, /PRODID:-\/\/BRASA Chile\/\/Boton Rojo\/\/ES\r\n/);
    assert.match(ics, /END:VCALENDAR\r\n$/);
    assert.ok(!ics.includes('\n') || ics.split('\r\n').every((l) => !l.includes('\n')));
  });
  test('un VEVENT por día con boton_rojo_hours, con fechas correctas', () => {
    const ics = botonRojoIcs({ comuna: 'Curicó', days });
    assert.equal(ics.match(/BEGIN:VEVENT/g).length, 2);
    assert.ok(ics.includes('DTSTART;VALUE=DATE:20260210\r\n'));
    assert.ok(ics.includes('DTEND;VALUE=DATE:20260211\r\n'));
    assert.ok(ics.includes('DTSTART;VALUE=DATE:20260212\r\n'));
    assert.ok(ics.includes('DTEND;VALUE=DATE:20260213\r\n'));
    assert.ok(!ics.includes('20260211T')); // el día sin horas no genera evento
    assert.ok(ics.includes('SUMMARY:Botón Rojo en Curicó\r\n'));
    const unfolded = ics.replaceAll('\r\n ', '');
    assert.ok(unfolded.includes('no significa que haya fuego'));
    assert.ok(unfolded.includes('CONAF · Botón Rojo'));
    assert.ok(ics.includes('UID:boton-rojo-Curicó-2026-02-10@brasa-chile'));
    assert.ok(ics.includes('DTSTAMP:'));
  });
  test('ninguna línea supera 75 octetos', () => {
    const ics = botonRojoIcs({ comuna: 'Curicó', days, url: 'https://brasa.example' });
    for (const line of ics.split('\r\n')) {
      assert.ok(new TextEncoder().encode(line).length <= 75, `línea: ${line}`);
    }
  });
  test('cruza de año: 31 de diciembre termina el 1 de enero', () => {
    const ics = botonRojoIcs({ comuna: 'X', days: [{ date: '2026-12-31', boton_rojo_hours: '10:00' }] });
    assert.ok(ics.includes('DTSTART;VALUE=DATE:20261231\r\n'));
    assert.ok(ics.includes('DTEND;VALUE=DATE:20270101\r\n'));
  });
  test('sin días con horas devuelve un calendario vacío válido', () => {
    const ics = botonRojoIcs({ comuna: 'Curicó', days: [{ date: '2026-02-10', boton_rojo_hours: null }] });
    assert.match(ics, /^BEGIN:VCALENDAR\r\n/);
    assert.match(ics, /END:VCALENDAR\r\n$/);
    assert.ok(!ics.includes('VEVENT'));
    assert.match(botonRojoIcs({ comuna: 'Curicó' }), /END:VCALENDAR\r\n$/);
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

describe('nearestPlacesText', () => {
  const inc = { lat: -33.45, lon: -70.66 };
  const at = (name, dLat) => ({ name, lat: inc.lat + dLat, lon: inc.lon }); // 0,01° de latitud ≈ 1,1 km

  test('sin lugares (o incidente sin coordenadas) devuelve null', () => {
    assert.equal(nearestPlacesText(inc, []), null);
    assert.equal(nearestPlacesText(inc, null), null);
    assert.equal(nearestPlacesText(null, [at('Casa', 0.05)]), null);
    assert.equal(nearestPlacesText({ lat: 'x', lon: -70.66 }, [at('Casa', 0.05)]), null);
  });
  test('un lugar cerca: nombre y km con un decimal (< 10 km)', () => {
    const r = nearestPlacesText(inc, [at('Casa de la abuela', 0.068)]); // ≈ 7,6 km
    assert.equal(r.nearest.name, 'Casa de la abuela');
    assert.equal(r.nearest.km, 7.6);
    assert.deepEqual(r.others, []);
  });
  test('tres o más: ordena por distancia y corta en top (nearest + 2)', () => {
    const r = nearestPlacesText(inc, [at('Lejos', 0.198), at('Media', 0.126), at('Cerca', 0.072), at('Otra', 0.09)]);
    assert.equal(r.nearest.name, 'Cerca');
    assert.equal(r.nearest.km, 8);
    assert.deepEqual(r.others.map((o) => o.name), ['Otra', 'Media']); // «Lejos» (22 km) queda fuera por top = 3
    assert.deepEqual(r.others.map((o) => o.km), [10, 14]);
  });
  test('un lugar a más de maxKm no aparece', () => {
    assert.equal(nearestPlacesText(inc, [at('Remoto', 0.54)]), null); // ≈ 60 km
    const r = nearestPlacesText(inc, [at('Cerca', 0.072), at('Remoto', 0.54)]);
    assert.equal(r.nearest.name, 'Cerca');
    assert.deepEqual(r.others, []);
  });
  test('un lugar a 30 km no entra en others (pero sí puede ser nearest)', () => {
    const r = nearestPlacesText(inc, [at('A 30 km', 0.27), at('Cerca', 0.045)]);
    assert.equal(r.nearest.name, 'Cerca');
    assert.deepEqual(r.others, []); // 30 km > 25 km
    assert.equal(nearestPlacesText(inc, [at('A 30 km', 0.27)]).nearest.km, 30);
  });
  test('ignora lugares sin coordenadas numéricas o sin nombre', () => {
    const r = nearestPlacesText(inc, [
      { name: 'Sin lat', lon: -70.66 },
      { name: 'Texto', lat: 'x', lon: -70.66 },
      { lat: inc.lat + 0.05, lon: inc.lon },
      { name: '  ', lat: inc.lat + 0.05, lon: inc.lon },
      at('Bien', 0.072),
    ]);
    assert.equal(r.nearest.name, 'Bien');
    assert.deepEqual(r.others, []);
  });
});
