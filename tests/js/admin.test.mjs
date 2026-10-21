/* Pruebas de web/js/admin.js con node:test: saludResumen y evidenciaCerca son puras, sin DOM ni fetch. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { evidenciaCerca, saludResumen } from '../../web/js/admin.js';

const sano = () => ({
  last_ingest_at: '2026-10-21T01:40:00Z',
  freshness: { last_ingest_at: '2026-10-21T01:40:00Z', age_seconds: 420, stale_after_s: 1800, stale: false },
  last_cycle: { started_at: '2026-10-21T01:39:00Z', finished_at: '2026-10-21T01:40:00Z', backup: true, work_backup: true },
  errors: { window_h: 24, by_product: {}, cycle_errors: [] },
});

describe('saludResumen', () => {
  test('respaldo caído y una fuente con fallos: problemas 2 y «qué hacer» con work.db.gz', () => {
    const status = sano();
    status.last_cycle = { ...status.last_cycle, backup: false, work_backup: false, backup_error: 'work: 500' };
    status.errors.by_product = { 'VIIRS NOAA-20': { runs: 8, failed: 1, last_failed_at: '2026-10-20T20:10:00Z' } };
    const r = saludResumen(status, { incidents: [] });
    assert.equal(r.problemas, 2);
    assert.ok(r.ciclo.que_hacer.includes('work.db.gz'));
    assert.ok(r.ciclo.que_hacer.includes('500'));
    assert.equal(r.fuentes[0].producto, 'VIIRS NOAA-20');
    assert.equal(r.fuentes[0].failed, 1);
  });

  test('un incendio oficial sin comuna no es «fuera de Chile»: va a sin_comuna con su «qué hacer»', () => {
    const inc = { id: 'inc-9', lat: -35.4, lon: -71.6, comuna_code: null, official_ref: 'CONAF-123', official_name: 'Incendio Talca' };
    const r = saludResumen(sano(), { incidents: [inc, { id: 'inc-1', lat: -33.4, lon: -70.6, comuna_code: '13101' }] });
    assert.equal(r.territorio.fuera, 0);
    assert.equal(r.territorio.sin_comuna, 1);
    assert.equal(r.territorio.muestra[0].id, 'inc-9');
    assert.equal(r.territorio.muestra[0].nombre, 'Incendio Talca');
    assert.equal(r.problemas, 1);
    assert.match(r.territorio.que_hacer, /emparejar la comuna/i);
  });

  test('un incidente sin comuna ni official_ref sí cuenta como fuera de Chile', () => {
    const inc = { id: 'inc-8', lat: -25.02, lon: -66.19, comuna_code: null, official_ref: null };
    const r = saludResumen(sano(), { incidents: [inc] });
    assert.equal(r.territorio.fuera, 1);
    assert.equal(r.territorio.sin_comuna, 0);
    assert.equal(r.territorio.muestra[0].id, 'inc-8');
    assert.equal(r.problemas, 1);
  });

  test('todo sano: problemas 0 y «al día»', () => {
    const r = saludResumen(sano(), { incidents: [{ id: 'i1', lat: -33.4, lon: -70.6, comuna_code: '13101' }] });
    assert.equal(r.problemas, 0);
    assert.equal(r.estado, 'al día');
    assert.equal(r.territorio.fuera, 0);
    assert.equal(r.ciclo.que_hacer, null);
  });

  test('la muestra de puntos fuera se corta en 5', () => {
    const incidents = Array.from({ length: 8 }, (_, i) => ({ id: `f${i}`, lat: -25 - i, lon: -66, comuna_code: null }));
    const r = saludResumen(sano(), { incidents });
    assert.equal(r.territorio.fuera, 8);
    assert.equal(r.territorio.muestra.length, 5);
  });

  test('work_backup en falso sin error no es problema (respaldo por hora, no cada ciclo)', () => {
    const status = sano();
    status.last_cycle.work_backup = false;
    const r = saludResumen(status, { incidents: [] });
    assert.equal(r.problemas, 0);
  });

  test('entradas vacías o nulas no lanzan', () => {
    for (const [s, i] of [[{}, {}], [null, null], [undefined, undefined], [{ last_cycle: null }, { incidents: null }]]) {
      const r = saludResumen(s, i);
      assert.equal(typeof r.problemas, 'number');
      assert.equal(r.territorio.fuera, 0);
    }
  });

  test('failures_24h trae last_error; se prefiere sobre errors.by_product', () => {
    const status = sano();
    status.failures_24h = { 'NOAA GOES': { runs: 6, failed: 2, last_failed_at: '2026-10-21T00:00:00Z', last_error: 'timeout S3' } };
    status.errors.by_product = { 'NOAA GOES': { runs: 6, failed: 2, last_failed_at: '2026-10-21T00:00:00Z' } };
    const r = saludResumen(status, { incidents: [] });
    assert.equal(r.fuentes[0].last_error, 'timeout S3');
    assert.equal(r.problemas, 1);
  });
});

const reporte = { lat: -35, lon: -71 };
const AHORA = Date.parse('2026-10-21T12:00:00Z');
const punto = (dLat, minutos, sensor = 'VIIRS') => ({
  lat: reporte.lat + dLat, lon: reporte.lon,
  observed_at: new Date(AHORA - minutos * 60000).toISOString(), sensor,
});

describe('evidenciaCerca', () => {
  test('una detección dentro del radio: distancia, edad y sensor', () => {
    const r = evidenciaCerca(reporte, [punto(0.0126, 20, 'ABI')], { ahora: AHORA });
    assert.equal(r.estado, 'detecciones');
    assert.equal(r.n, 1);
    assert.equal(r.cerca[0].minutos, 20);
    assert.equal(r.cerca[0].sensor, 'GOES');
    assert.equal(r.texto, '1 detección a 1,4 km · hace 20 min (GOES)');
  });

  test('una detección fuera del radio no cuenta y se dice la ventana', () => {
    const r = evidenciaCerca(reporte, [punto(0.2, 20)], { ahora: AHORA });
    assert.equal(r.estado, 'sin_detecciones');
    assert.equal(r.n, 0);
    assert.equal(r.texto, 'Sin detecciones a menos de 10 km en las últimas 6 h');
  });

  test('lista vacía: «sin detecciones» con el radio y la ventana explícitos', () => {
    const r = evidenciaCerca(reporte, [], { ahora: AHORA });
    assert.equal(r.estado, 'sin_detecciones');
    assert.deepEqual(r.cerca, []);
    assert.equal(r.texto, 'Sin detecciones a menos de 10 km en las últimas 6 h');
  });

  test('puntos null (la consulta falló): «no se pudo consultar», nunca «no hay fuego»', () => {
    const r = evidenciaCerca(reporte, null, { ahora: AHORA });
    assert.equal(r.estado, 'error');
    assert.equal(r.n, 0);
    assert.equal(r.texto, 'No se pudo consultar la evidencia satelital');
  });

  test('tres detecciones: se informa el total y la más cercana en metros', () => {
    const r = evidenciaCerca(reporte, [punto(0.05, 90), punto(0.008094, 20), punto(0.03, 45)], { ahora: AHORA });
    assert.equal(r.estado, 'detecciones');
    assert.equal(r.n, 3);
    assert.ok(r.cerca[0].km > 0.85 && r.cerca[0].km < 0.95);
    assert.equal(r.texto, '3 detecciones, la más cercana a 900 m');
  });
});
