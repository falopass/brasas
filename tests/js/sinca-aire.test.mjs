/* Pruebas de airLine en web/js/views/zona.js (OFI-35): lectura horaria SINCA, MP10, CO,
 * distinción humo/polvo/mixto, respaldo reciente y retrocompatibilidad con el formato antiguo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { addEventListener() {} }; // no pisar el stub de otra suite
if (typeof globalThis.window.addEventListener !== 'function') {
  globalThis.window.addEventListener = () => {};
}

const { airLine } = await import('../../web/js/views/zona.js');

const BASE_AIR = {
  name: 'Talca',
  code: '709',
  comuna: 'Talca',
  distance_km: 3.4,
  lat: -35.43,
  lon: -71.67,
  observed_at: '2026-10-20T18:00:00Z',
  pm25: 182.5,
  pm25_period: 'horario',
  pm25_24h: 34.2,
  pm10: 210.3,
  pm10_unit: 'µg/m³',
  pm10_observed_at: '2026-10-20T18:00:00Z',
  co: 2.45,
  co_unit: 'ppm',
  co_observed_at: '2026-10-20T18:00:00Z',
  signal: 'humo',
  icap: 145,
  status: 'Alerta',
  preliminar: true,
  source_mode: 'live',
};

describe('airLine (OFI-35 · SINCA horario, MP10 y CO)', () => {
  test('sin dato, sin pm25 o sin observed_at devuelve cadena vacía', () => {
    assert.equal(airLine(null), '');
    assert.equal(airLine(undefined), '');
    assert.equal(airLine({}), '');
    assert.equal(airLine({ air: null }), '');
    assert.equal(airLine({ air: { ...BASE_AIR, pm25: null } }), '');
    assert.equal(airLine({ air: { ...BASE_AIR, pm25: undefined } }), '');
    assert.equal(airLine({ air: { ...BASE_AIR, pm25: Number.NaN } }), '');
    assert.equal(airLine({ air: { ...BASE_AIR, observed_at: '' } }), '');
    assert.equal(airLine({ air: { ...BASE_AIR, observed_at: null } }), '');
  });

  test('lectura horaria con MP10, CO y señal de humo muestra todos los campos en dos niveles sin afirmar incendio', () => {
    const out = String(airLine({ air: BASE_AIR }));
    assert.ok(out.includes('<b>Aire medido en la estación Talca</b>'));
    assert.ok(out.includes('(Talca, a 3,4 km)'));
    assert.ok(out.includes('en la última hora'));
    assert.ok(out.includes('partículas finas (MP2,5) 182,5 µg/m³'));
    assert.ok(out.includes('MP2,5 horario 182,5 µg/m³'));
    assert.ok(out.includes('media 24 h: 34,2 µg/m³'), 'el nivel técnico muestra la media 24 h cuando difiere');
    assert.ok(out.includes('polvo grueso (MP10) 210,3 µg/m³'));
    assert.ok(out.includes('MP10 210,3 µg/m³'));
    assert.ok(out.includes('monóxido de carbono (CO) 2,45 ppm'));
    assert.ok(out.includes('CO 2,45 ppm'));
    assert.ok(out.includes('posible humo (puede venir de leña, quemas o un incendio)'));
    assert.ok(out.includes('no distingue leña de incendio'));
    assert.ok(out.includes('ICAP 24 h 145 (Alerta)'));
    assert.ok(out.includes('calidad del aire (promedio de 24 h): Alerta'));
    assert.ok(out.includes('href="https://sinca.mma.gob.cl/"'));
    assert.ok(out.includes('target="_blank"') && out.includes('rel="noopener"'));
    assert.ok(out.includes('Medición preliminar del MMA, no un pronóstico.'));
    assert.ok(!out.includes('respaldo reciente'), 'en modo live no marca respaldo');
    assert.ok(!out.includes('undefined') && !out.includes('NaN'));
  });

  test('lectura de polvo (signal: polvo) distingue polvo sin afirmar humo', () => {
    const out = String(airLine({
      air: {
        ...BASE_AIR,
        pm25: 18.4,
        pm25_24h: 18.4,
        pm10: 165.2,
        co: null,
        co_unit: null,
        signal: 'polvo',
        icap: 40,
        status: 'Bueno',
      },
    }));
    assert.ok(out.includes('posible polvo en suspensión'));
    assert.ok(out.includes('MP10 ≥ 80 µg/m³ y MP2,5/MP10 &lt; 0,35, sin CO alto'));
    assert.ok(out.includes('MP10 165,2 µg/m³'));
    assert.ok(!out.toLowerCase().includes('humo'), 'no debe afirmar humo cuando la señal es polvo');
    assert.ok(!out.includes('monóxido de carbono') && !/\bCO \d/.test(out), 'sin CO no pinta el campo CO');
    assert.ok(!out.includes('media 24 h:'), 'si pm25_24h coincide con el horario no se repite');
  });

  test('señal mixta y media 24 h con modo snapshot indican respaldo reciente sin inventar horas', () => {
    const out = String(airLine({
      air: {
        ...BASE_AIR,
        pm25_period: '24h',
        pm25_24h: 72.1,
        pm25: 72.1,
        signal: 'mixto',
        source_mode: 'snapshot',
      },
    }));
    assert.ok(out.includes('media 24 h'));
    assert.ok(!out.includes('última hora'));
    assert.ok(out.includes('posible mezcla de humo y polvo'));
    assert.ok(out.includes('MP2,5 ≥ 25 y MP10 ≥ 80 µg/m³, con cociente entre 0,35 y 0,65'));
    assert.ok(out.includes('respaldo reciente'));
  });

  test('retrocompatibilidad y claves heredadas de Object en signal no producen undefined ni NaN', () => {
    const out = String(airLine({
      air: {
        name: 'Parque O’Higgins',
        comuna: null,
        distance_km: 1.8,
        observed_at: '2026-10-20T18:00:00Z',
        pm25: 24.6,
        icap: 62,
        status: 'Regular',
        signal: 'constructor',
      },
    }));
    assert.ok(out.includes('Aire medido en la estación Parque O’Higgins'));
    assert.ok(out.includes('(SINCA, a 1,8 km)'));
    assert.ok(out.includes('MP2,5 24,6 µg/m³'));
    assert.ok(out.includes('ICAP 24 h 62 (Regular)'));
    assert.ok(!out.includes('MP10'));
    assert.ok(!out.includes('CO '));
    assert.ok(!out.includes('undefined'));
    assert.ok(!out.includes('NaN'));
  });

  test('escapa HTML en campos de texto de la estación y unidades', () => {
    const out = String(airLine({
      air: {
        ...BASE_AIR,
        name: '<img src=x>',
        comuna: '<b>Comuna</b>',
        pm10_unit: '<script>',
        status: '<em>X</em>',
      },
    }));
    assert.ok(!out.includes('<img src=x>'));
    assert.ok(!out.includes('<b>Comuna</b>'));
    assert.ok(!out.includes('<script>'));
    assert.ok(!out.includes('<em>X</em>'));
    assert.ok(out.includes('&lt;img src=x&gt;'));
  });
});
