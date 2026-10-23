/* Pruebas de web/js/satelite.js con node:test, sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { esReciente, hayImagen, sliderUrl, thermalUrl, worldviewLayer, worldviewUrl } from '../../web/js/satelite.js';

// Casos reales de web/data/cases.json
const VINA = { bbox: [-71.75, -33.25, -71.2, -32.95], start: '2024-02-02T12:00:00Z', end: '2024-02-05T12:00:00Z' };
const PAINE = { bbox: [-73.3, -51.3, -72.7, -50.85], start: '2011-12-27T12:00:00Z', end: '2012-01-15T12:00:00Z' };
const MAQUINAS = { bbox: [-72.75, -36.15, -71.85, -35.15], start: '2017-01-18T12:00:00Z', end: '2017-02-05T12:00:00Z' };

const NOW = Date.parse('2026-10-21T15:00:00Z');
const hace = (horas) => new Date(NOW - horas * 3600 * 1000).toISOString();

describe('worldviewUrl', () => {
  test('Viña del Mar 2024: URL exacta (VIIRS, caso posterior a 2015-11-24)', () => {
    assert.equal(worldviewUrl(VINA), 'https://worldview.earthdata.nasa.gov/?v=-71.75,-33.25,-71.2,-32.95&t=2024-02-05-T12%3A00%3A00Z&l=VIIRS_SNPP_CorrectedReflectance_TrueColor');
  });
  test('Torres del Paine 2011: URL exacta (MODIS Aqua, VIIRS aún sin datos)', () => {
    assert.equal(worldviewUrl(PAINE), 'https://worldview.earthdata.nasa.gov/?v=-73.3,-51.3,-72.7,-50.85&t=2012-01-15-T12%3A00%3A00Z&l=MODIS_Aqua_CorrectedReflectance_TrueColor');
  });
  test('v= respeta el orden oeste,sur,este,norte y t= la fecha ISO del caso', () => {
    const url = new URL(worldviewUrl(VINA));
    assert.equal(url.searchParams.get('v'), '-71.75,-33.25,-71.2,-32.95');
    assert.equal(url.searchParams.get('t'), '2024-02-05-T12:00:00Z'); // SAT-01: end posterior gana sobre start
  });
  test('redondea el bbox a 3 decimales', () => {
    const url = new URL(worldviewUrl({ ...VINA, bbox: [-71.7549, -33.2504, -71.2006, -32.95] }));
    assert.equal(url.searchParams.get('v'), '-71.755,-33.25,-71.201,-32.95');
  });
  test('ninguna URL lleva undefined ni NaN', () => {
    for (const url of [worldviewUrl(VINA), worldviewUrl(PAINE), sliderUrl({ satellite: 'G19', end: hace(1), ahora: NOW })]) {
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
  test('GOES del caso en disco completo, solo si el bucle en vivo lo cubre (48 h)', () => {
    assert.equal(sliderUrl({ satellite: 'G19', end: hace(1), ahora: NOW }), 'https://slider.cira.colostate.edu/?sat=goes-19&sec=full_disk');
    assert.equal(sliderUrl({ satellite: 'G16', end: hace(48), ahora: NOW }), 'https://slider.cira.colostate.edu/?sat=goes-16&sec=full_disk');
  });
  test('sin satélite o sin fecha de término reciente devuelve null', () => {
    assert.equal(sliderUrl({}), null);
    assert.equal(sliderUrl({ satellite: null }), null);
    assert.equal(sliderUrl(), null);
    // Sin `end` no se puede asegurar que el bucle de hoy muestra el caso.
    assert.equal(sliderUrl({ satellite: 'G19' }), null);
  });
});

describe('el visor se ofrece solo si puede mostrar la escena del caso', () => {
  test('caso histórico (Las Máquinas 2017): Worldview sí, SLIDER no', () => {
    assert.ok(worldviewUrl({ ...MAQUINAS, ahora: NOW }));
    assert.equal(sliderUrl({ satellite: 'G16', end: MAQUINAS.end, ahora: NOW }), null);
  });
  test('caso que empezó hace 3 h: Worldview no tiene la imagen todavía', () => {
    assert.equal(worldviewUrl({ bbox: VINA.bbox, start: hace(3), end: hace(0), ahora: NOW }), null);
    assert.equal(hayImagen(hace(3), NOW), false);
  });
  test('caso de hace 2 días: ambos válidos', () => {
    const caso = { bbox: VINA.bbox, start: hace(50), end: hace(48), ahora: NOW };
    assert.ok(worldviewUrl(caso));
    assert.ok(sliderUrl({ satellite: 'G19', end: caso.end, ahora: NOW }));
    assert.ok(esReciente(caso.end, NOW));
  });
  test('fecha inválida: ambos nulos', () => {
    assert.equal(worldviewUrl({ bbox: VINA.bbox, start: 'no es fecha', end: hace(2), ahora: NOW }), null);
    assert.equal(sliderUrl({ satellite: 'G19', end: 'no es fecha', ahora: NOW }), null);
    assert.equal(hayImagen('no es fecha', NOW), false);
    assert.equal(esReciente('no es fecha', NOW), false);
  });
});

describe('thermalUrl (SAT-01)', () => {
  test('VIIRS térmico a la hora exacta de la detección (>= 2015-11-24)', () => {
    assert.equal(thermalUrl({ bbox: VINA.bbox, at: '2024-02-02T14:30:00Z' }),
      'https://worldview.earthdata.nasa.gov/?v=-71.75,-33.25,-71.2,-32.95&t=2024-02-02-T14%3A30%3A00Z&l=VIIRS_SNPP_ThermalAnomalies');
  });
  test('MODIS térmico para fechas anteriores a VIIRS', () => {
    assert.equal(thermalUrl({ bbox: PAINE.bbox, at: '2011-12-27T15:00:00Z' }),
      'https://worldview.earthdata.nasa.gov/?v=-73.3,-51.3,-72.7,-50.85&t=2011-12-27-T15%3A00%3A00Z&l=MODIS_Aqua_ThermalAnomalies');
  });
  test('sin bbox válido o at legible devuelve null', () => {
    assert.equal(thermalUrl({ bbox: VINA.bbox, at: 'mal' }), null);
    assert.equal(thermalUrl({ at: VINA.start }), null);
    assert.equal(thermalUrl(), null);
  });
});

describe('worldviewUrl con layer y end (SAT-01)', () => {
  test('t= usa end cuando es posterior a start', () => {
    const url = new URL(worldviewUrl(VINA));
    assert.equal(url.searchParams.get('t'), '2024-02-05-T12:00:00Z');
  });
  test('layer opcional sustituye la capa por defecto', () => {
    const url = new URL(worldviewUrl({ ...VINA, layer: 'X_Capa' }));
    assert.equal(url.searchParams.get('l'), 'X_Capa');
  });
  test('end anterior a start conserva t=start', () => {
    const url = new URL(worldviewUrl({ ...VINA, end: VINA.start }));
    assert.equal(url.searchParams.get('t'), '2024-02-02-T12:00:00Z');
  });
  test('ninguna URL nueva lleva undefined ni NaN', () => {
    for (const url of [thermalUrl({ bbox: VINA.bbox, at: VINA.start }), worldviewUrl({ ...VINA, layer: 'X' }), sliderUrl({ satellite: 'G19', end: hace(1), sector: 'conus', ahora: NOW })]) {
      assert.doesNotMatch(url, /undefined|NaN/);
    }
  });
});

describe('sliderUrl con sector (SAT-01)', () => {
  test('sector opcional, full_disk por defecto', () => {
    assert.equal(sliderUrl({ satellite: 'G19', end: hace(1), sector: 'sector_chile', ahora: NOW }),
      'https://slider.cira.colostate.edu/?sat=goes-19&sec=sector_chile');
  });
});
