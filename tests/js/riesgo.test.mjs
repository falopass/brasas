/* Pruebas de forecastAge y de la temporada reciente en web/js/views/riesgo.js con node:test,
 * sin navegador. riesgo.js importa ui.js, que registra un listener «online» al cargar: se usa
 * un stub, igual que en zona.test.mjs (index.js junta todas las suites en un proceso). */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { addEventListener() {} }; // no pisar el stub de otra suite
const { forecastAge, historiaPanel, recentSeason } = await import('../../web/js/views/riesgo.js');

const NOW = Date.parse('2026-10-21T00:00:00Z');
const hoursAgo = (h) => new Date(NOW - h * 3600000).toISOString();

describe('forecastAge', () => {
  test('un pronóstico de hace 1 h está al día', () => {
    assert.deepEqual(forecastAge(hoursAgo(1), NOW), { horas: 1, nivel: 'al-dia' });
  });
  test('uno de hace 7 h quedó atrasado', () => {
    assert.equal(forecastAge(hoursAgo(7), NOW).nivel, 'atrasado');
    assert.equal(forecastAge(hoursAgo(7), NOW).horas, 7);
  });
  test('uno de hace 30 h cuenta como sin dato', () => {
    assert.equal(forecastAge(hoursAgo(30), NOW).nivel, 'sin-dato');
  });
  test('sin computed_at no hay dato', () => {
    assert.equal(forecastAge(undefined, NOW).nivel, 'sin-dato');
    assert.equal(forecastAge(null, NOW).nivel, 'sin-dato');
    assert.equal(forecastAge('', NOW).nivel, 'sin-dato');
  });
  test('una fecha ilegible no lanza y cuenta como sin dato', () => {
    assert.equal(forecastAge('no-es-fecha', NOW).nivel, 'sin-dato');
    assert.equal(forecastAge('2026-13-99T99:99', NOW).nivel, 'sin-dato');
  });
  test('los bordes son exactos: < 6 h al día, 6–24 h atrasado, > 24 h sin dato', () => {
    assert.equal(forecastAge(hoursAgo(5.99), NOW).nivel, 'al-dia');
    assert.equal(forecastAge(hoursAgo(6), NOW).nivel, 'atrasado');
    assert.equal(forecastAge(hoursAgo(24), NOW).nivel, 'atrasado');
    assert.equal(forecastAge(hoursAgo(24.01), NOW).nivel, 'sin-dato');
  });
  test('una fecha en el futuro no da horas negativas', () => {
    assert.deepEqual(forecastAge(new Date(NOW + 3600000).toISOString(), NOW), { horas: 0, nivel: 'al-dia' });
  });
  test('una fecha ISO sin Z se lee como UTC', () => {
    assert.equal(forecastAge('2026-10-20T23:00:00', NOW).nivel, 'al-dia');
  });
});

const TEMPORADA = {
  temporada: '2025-2026',
  source: 'https://raw.githubusercontent.com/deigeprif/public/main/reporte/incendios_totales_25_26.csv',
  fetched_at: '2026-10-19T22:34:11+00:00',
  comunas: [{ code: 7101, name: 'Talca', region: 'Maule', incendios: 42, hectareas: 1234.5, mes_peak: '2026-01', max_ha: 800 }],
};

describe('temporada reciente (OFI-206)', () => {
  test('encuentra la comuna por código', () => {
    const r = recentSeason(TEMPORADA, 7101);
    assert.equal(r.incendios, 42);
    assert.equal(r.temporada, '2025-2026');
    assert.equal(r.source, TEMPORADA.source);
  });
  test('sin fila o sin archivo devuelve null', () => {
    assert.equal(recentSeason(TEMPORADA, 9999), null);
    assert.equal(recentSeason(null, 7101), null);
  });
  test('el panel muestra la temporada con su fuente y fecha, separada del histórico', () => {
    const out = String(historiaPanel(null, 'Nota histórica.', recentSeason(TEMPORADA, 7101)));
    assert.ok(out.includes('2025-26'));
    assert.ok(out.includes('42 incendios'));
    assert.ok(out.includes('1.234,5 ha'));
    assert.ok(out.includes('CONAF GEPRIF'));
    assert.ok(out.includes('19 oct'));
    assert.ok(out.includes('2024-2025'), 'debe explicar el hueco de la temporada faltante');
  });
});
