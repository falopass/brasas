/* Pruebas de web/js/satelite.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { sliderUrl, worldviewLayer, worldviewUrl } from '../../web/js/satelite.js';

// Casos reales de web/data/cases.json
const VINA = { bbox: [-71.75, -33.25, -71.2, -32.95], start: '2024-02-02T12:00:00Z', end: '2024-02-05T12:00:00Z' };
const PAINE = { bbox: [-73.3, -51.3, -72.7, -50.85], start: '2011-12-27T12:00:00Z', end: '2012-01-15T12:00:00Z' };

describe('worldviewUrl', () => {
  test('Viña del Mar 2024: URL exacta (VIIRS, caso posterior a 2015-11-24)', () => {
    assert.equal(worldviewUrl(VINA), 'https://worldview.earthdata.nasa.gov/?v=-71.75,-33.25,-71.2,-32.95&t=2024-02-02-T12%3A00%3A00Z&l=VIIRS_SNPP_CorrectedReflectance_TrueColor');
  });
  test('Torres del Paine 2011: URL exacta (MODIS Aqua, VIIRS aún sin datos)', () => {
    assert.equal(worldviewUrl(PAINE), 'https://worldview.earthdata.nasa.gov/?v=-73.3,-51.3,-72.7,-50.85&t=2011-12-27-T12%3A00%3A00Z&l=MODIS_Aqua_CorrectedReflectance_TrueColor');
  });
  test('v= respeta el orden oeste,sur,este,norte y t= la fecha ISO del caso', () => {
    const url = new URL(worldviewUrl(VINA));
    assert.equal(url.searchParams.get('v'), '-71.75,-33.25,-71.2,-32.95');
    assert.equal(url.searchParams.get('t'), '2024-02-02-T12:00:00Z');
  });
  test('redondea el bbox a 3 decimales', () => {
    const url = new URL(worldviewUrl({ ...VINA, bbox: [-71.7549, -33.2504, -71.2006, -32.95] }));
    assert.equal(url.searchParams.get('v'), '-71.755,-33.25,-71.201,-32.95');
  });
  test('ninguna URL lleva undefined ni NaN', () => {
    for (const url of [worldviewUrl(VINA), worldviewUrl(PAINE), sliderUrl({ satellite: 'G19' })]) {
      assert.ok(!url.includes('undefined') && !url.includes('NaN'), url);
    }
  });
  test('sin bbox o sin fechas devuelve null', () => {
    assert.equal(worldviewUrl({ start: VINA.start, end: VINA.end }), null);
    assert.equal(worldviewUrl({ bbox: [-71.7, -33.2, -71.2], start: VINA.start, end: VINA.end }), null);
    assert.equal(worldviewUrl({ bbox: VINA.bbox, end: VINA.end }), null);
    assert.equal(worldviewUrl({ bbox: VINA.bbox, start: VINA.start }), null);
    assert.equal(worldviewUrl({ bbox: VINA.bbox, start: 'no es fecha', end: VINA.end }), null);
    assert.equal(worldviewUrl(), null);
  });
});

describe('worldviewLayer', () => {
  test('elige la capa con datos según la fecha del caso', () => {
    assert.equal(worldviewLayer('2024-02-02T12:00:00Z'), 'VIIRS_SNPP_CorrectedReflectance_TrueColor');
    assert.equal(worldviewLayer('2011-12-27T12:00:00Z'), 'MODIS_Aqua_CorrectedReflectance_TrueColor');
  });
});

describe('sliderUrl', () => {
  test('GOES del caso en disco completo', () => {
    assert.equal(sliderUrl({ satellite: 'G19' }), 'https://slider.cira.colostate.edu/?sat=goes-19&sec=full_disk');
    assert.equal(sliderUrl({ satellite: 'G16' }), 'https://slider.cira.colostate.edu/?sat=goes-16&sec=full_disk');
  });
  test('sin satélite devuelve null', () => {
    assert.equal(sliderUrl({}), null);
    assert.equal(sliderUrl({ satellite: null }), null);
    assert.equal(sliderUrl(), null);
  });
});
