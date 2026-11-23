/* Pruebas de airCallout (RISK-25: señal humo/polvo y detalle técnico CAMS) y
 * atmosphereCallout (RISK-24: Índice de Haines, VPD, humedad del suelo y CAPE)
 * en web/js/views/riesgo.js con node:test, sin navegador. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window ??= { addEventListener() {} }; // no pisar el stub de otra suite
const { airCallout, atmosphereCallout } = await import('../../web/js/views/riesgo.js');

const BASE_AIR = {
  pm25_today_max: 12.4,
  pm25_tomorrow_max: 10.2,
  pm10_today_max: 28.5,
  co_today_max: 620,
  aod_today_max: 0.42,
  dust_today_max: 14.3,
  unit: 'µg/m³',
  units: { pm25: 'µg/m³', pm10: 'µg/m³', co: 'µg/m³', aod: 'adimensional', dust: 'µg/m³' },
  guideline: { pm25_24h: 15, name: 'Guía OMS 2021' },
  source: { name: 'CAMS vía Open-Meteo', url: 'https://open-meteo.com/en/docs/air-quality-api' },
  fetched_at: '2026-11-23T15:00:00Z',
};

describe('airCallout · señal humo/polvo y detalle técnico CAMS', () => {
  test('signal humo marca callout-warn, usa dual y aclara que no distingue leña de incendio', () => {
    const out = String(airCallout({ ...BASE_AIR, signal: 'humo' }));
    assert.match(out, /class="callout callout-warn"/);
    assert.match(out, /class="x-plain"/);
    assert.match(out, /class="x-tech"/);
    assert.match(out, /humo de combustión/i);
    assert.match(out, /leña/i);
    assert.match(out, /incendio forestal/i);
    assert.match(out, /MP2,5 y CO elevados/);
    assert.match(out, /MP10 28,5 µg\/m³/);
    assert.match(out, /CO 620 µg\/m³/);
    assert.match(out, /AOD 0,42 adimensional/);
    assert.match(out, /Polvo 14,3 µg\/m³/);
    assert.match(out, /pronóstico del modelo CAMS/i);
    assert.ok(out.includes('href="https://sinca.mma.gob.cl/"'));
    assert.ok(out.includes('Ministerio del Medio Ambiente'));
    assert.doesNotMatch(out, /\bundefined\b|\bNaN\b/);
  });

  test('signal polvo informa polvo en suspensión sin marcar callout-warn cuando MP2,5 está bajo el límite', () => {
    const out = String(airCallout({ ...BASE_AIR, signal: 'polvo', pm25_today_max: 11, co_today_max: 190, dust_today_max: 85.4 }));
    assert.match(out, /class="callout"/);
    assert.doesNotMatch(out, /callout-warn/);
    assert.match(out, /<b>Polvo y aire · MP2,5<\/b>/);
    assert.match(out, /polvo en suspensión/i);
    assert.match(out, /sin CO alto/);
    assert.match(out, /Polvo 85,4 µg\/m³/);
    assert.match(out, /pronóstico del modelo CAMS/i);
    assert.ok(out.includes('href="https://sinca.mma.gob.cl/"'));
    assert.doesNotMatch(out, /\bundefined\b|\bNaN\b/);
  });

  test('signal null conserva MP2,5, atribución CAMS vs SINCA y omite variables faltantes sin NaN', () => {
    const out = String(airCallout({
      pm25_today_max: 9.4,
      pm25_tomorrow_max: 12.1,
      pm10_today_max: 21.3,
      co_today_max: null,
      aod_today_max: undefined,
      dust_today_max: Number.NaN,
      signal: null,
      source: BASE_AIR.source,
    }));
    assert.match(out, /class="callout"/);
    assert.doesNotMatch(out, /callout-warn/);
    assert.doesNotMatch(out, /humo de combustión|polvo en suspensión/i);
    assert.match(out, /MP10 21,3 µg\/m³/);
    assert.doesNotMatch(out, /\bCO\b|\bAOD\b|\bPolvo\b/);
    assert.match(out, /CAMS vía Open-Meteo/);
    assert.ok(out.includes('Ver la calidad del aire medida en SINCA'));
    assert.doesNotMatch(out, /\bundefined\b|\bNaN\b/);
  });

  test('null o undefined devuelve cadena vacía', () => {
    assert.equal(airCallout(null), '');
    assert.equal(airCallout(undefined), '');
  });
});

describe('atmosphereCallout', () => {
  const HAINES_6 = {
    haines: {
      index: 6,
      level: 'alto',
      variant: 'media',
      levels_hpa: '850-700',
      stability: 3,
      moisture: 3,
      lapse_c: 12.4,
      dewpoint_depression_c: 15.1,
    },
    vpd_kpa: 3.2,
    soil_moisture_0_to_1cm: 0.08,
    soil_moisture_0_to_7cm: 0.12,
    cape_j_kg: 450.0,
    observed_at: '2026-11-23T18:00:00Z',
    fetched_at: '2026-11-23T15:00:00Z',
    model: 'ecmwf_ifs025',
    source: { name: 'Open-Meteo · ECMWF IFS', url: 'https://open-meteo.com/en/docs' },
  };

  test('con Haines 6 muestra callout-warn, dual, métricas y fuente Open-Meteo ECMWF IFS', () => {
    const out = String(atmosphereCallout(HAINES_6));
    assert.match(out, /class="callout callout-warn"/);
    assert.match(out, /class="x-plain"/);
    assert.match(out, /class="x-tech"/);
    assert.match(out, /Haines 6\/6/);
    assert.match(out, /850-700 hPa/);
    assert.match(out, /ΔT 12,4 °C/);
    assert.match(out, /T-Td 15,1 °C/);
    assert.match(out, /3,2 kPa/);
    assert.match(out, /0,08 m³\/m³/);
    assert.match(out, /0,12 m³\/m³/);
    assert.match(out, /Inestabilidad para tormentas: baja/);
    assert.match(out, /el fuego podría crecer: alto/);
    assert.match(out, /450 J\/kg/);
    assert.match(out, /pico previsto/);
    assert.match(out, /hora de Chile continental/);
    assert.ok(out.includes('Open-Meteo · ECMWF IFS'));
    assert.ok(out.includes('href="https://open-meteo.com/en/docs"'));
    assert.ok(out.includes('target="_blank"') && out.includes('rel="noopener"'));
    assert.doesNotMatch(out, /\bundefined\b|\bNaN\b/);
  });

  test('con observed_at futuro y fetched_at anterior no dice «recién»', () => {
    const future = new Date(Date.now() + 3 * 3600 * 1000).toISOString();
    const past = new Date(Date.now() - 25 * 60 * 1000).toISOString();
    const out = String(atmosphereCallout({ ...HAINES_6, observed_at: future, fetched_at: past }));
    assert.match(out, /pico previsto/);
    assert.match(out, /consultado hace 25 min/);
    assert.doesNotMatch(out, /recién/);
  });

  test('con datos parciales pinta solo lo presente y no produce undefined ni NaN', () => {
    const out = String(atmosphereCallout({
      haines: null,
      vpd_kpa: 1.8,
      soil_moisture_0_to_1cm: 0.15,
      soil_moisture_0_to_7cm: null,
      cape_j_kg: 120,
      fetched_at: '2026-11-23T15:00:00Z',
    }));
    assert.match(out, /class="callout"/);
    assert.doesNotMatch(out, /callout-warn/);
    assert.match(out, /1,8 kPa/);
    assert.match(out, /15 % \(0–1 cm\)/);
    assert.match(out, /0,15 m³\/m³/);
    assert.match(out, /120 J\/kg/);
    assert.doesNotMatch(out, /Haines|0–7 cm/);
    assert.ok(out.includes('Open-Meteo · ECMWF IFS'));
    assert.doesNotMatch(out, /\bundefined\b|\bNaN\b/);
  });

  test('sin datos válidos devuelve cadena vacía', () => {
    assert.equal(atmosphereCallout(null), '');
    assert.equal(atmosphereCallout(undefined), '');
    assert.equal(atmosphereCallout({}), '');
    assert.equal(atmosphereCallout({ haines: { index: null }, vpd_kpa: null }), '');
  });
});
