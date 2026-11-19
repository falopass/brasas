/* Pruebas de web/js/gibs.js (MAPA-180), sin navegador ni dependencias. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { GIBS, GIBS_HIST, gibsTileUrl, fechaGibs, tiempoGibs, escenaCaso, GIBS_ATTRIBUTION } from '../../web/js/gibs.js';

describe('registro de capas GIBS', () => {
  test('las tres capas del mapa en vivo existen con su TileMatrixSet único', () => {
    assert.deepEqual(Object.keys(GIBS), ['goes', 'viirs', 'aod']);
    for (const def of Object.values(GIBS)) {
      assert.match(def.layer, /^[A-Z]/, `${def.key}: nombre de capa GIBS`);
      assert.match(def.matrix, /^GoogleMapsCompatible_Level\d+$/, `${def.key}: matriz`);
      assert.equal(def.maxzoom, Number(def.matrix.slice(-1)), `${def.key}: maxzoom = nivel de la matriz`);
      assert.ok(def.maxzoom >= 1 && def.maxzoom <= 9);
      assert.ok(['png', 'jpg'].includes(def.ext));
      assert.ok(['subdiaria', 'diaria'].includes(def.tipo));
    }
  });
  test('GOES GeoColor es subdiaria y VIIRS/aerosol diarias', () => {
    assert.equal(GIBS.goes.tipo, 'subdiaria');
    assert.equal(GIBS.viirs.tipo, 'diaria');
    assert.equal(GIBS.aod.tipo, 'diaria');
  });
  test('la atribución exige el crédito de NASA EOSDIS', () => {
    assert.match(GIBS_ATTRIBUTION, /Global Imagery Browse Services \(GIBS\), part of NASA EOSDIS/);
  });
});

describe('gibsTileUrl', () => {
  test('arma la URL WMTS con el orden TileMatrix/TileRow/TileCol ({z}/{y}/{x})', () => {
    const url = gibsTileUrl(GIBS.goes, 'default')[0];
    assert.equal(url, 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/GOES-East_ABI_GeoColor/default/default/GoogleMapsCompatible_Level7/{z}/{y}/{x}.png');
  });
  test('una fecha diaria queda en el segmento de tiempo y el formato de la capa', () => {
    const url = gibsTileUrl(GIBS.viirs, '2026-11-17')[0];
    assert.ok(url.includes('/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/2026-11-17/'));
    assert.ok(url.endsWith('.jpg'));
  });
});

describe('fechaGibs / tiempoGibs', () => {
  const ahora = new Date('2026-11-19T15:00:00Z');
  test('«hoy» y «ayer» son días UTC consecutivos', () => {
    assert.equal(fechaGibs('hoy', ahora), '2026-11-19');
    assert.equal(fechaGibs('ayer', ahora), '2026-11-18');
    assert.equal(fechaGibs('ayer', ahora), fechaGibs('hoy', new Date('2026-11-18T15:00:00Z')));
  });
  test('una fecha inválida devuelve null', () => {
    assert.equal(fechaGibs('hoy', 'no-fecha'), null);
  });
  test('la capa subdiaria siempre usa `default`; la diaria, el día elegido', () => {
    assert.equal(tiempoGibs(GIBS.goes, 'hoy', ahora), 'default');
    assert.equal(tiempoGibs(GIBS.viirs, 'hoy', ahora), '2026-11-19');
    assert.equal(tiempoGibs(GIBS.viirs, 'ayer', ahora), '2026-11-18');
    assert.equal(tiempoGibs(GIBS.aod, 'ayer', ahora), '2026-11-18');
  });
});

describe('escenaCaso', () => {
  const ahora = Date.parse('2026-11-19T00:00:00Z');
  test('un caso reciente usa VIIRS S-NPP y un antiguo MODIS Aqua', () => {
    const reciente = escenaCaso('2024-02-02T13:00:00Z', ahora);
    assert.equal(reciente.key, 'viirs');
    assert.equal(reciente.date, '2024-02-02');
    assert.equal(reciente.def, GIBS_HIST.viirs);
    const antiguo = escenaCaso('2010-01-15T13:00:00Z', ahora);
    assert.equal(antiguo.key, 'modis');
    assert.equal(antiguo.date, '2010-01-15');
  });
  test('sin fecha válida, en el futuro o antes de la cobertura devuelve null', () => {
    assert.equal(escenaCaso('', ahora), null);
    assert.equal(escenaCaso('no-es-fecha', ahora), null);
    assert.equal(escenaCaso('2027-01-01T00:00:00Z', ahora), null); // futuro
    assert.equal(escenaCaso('1990-01-01T00:00:00Z', ahora), null); // antes de MODIS Aqua (2002)
  });
  test('el día del caso se toma en UTC y las capas históricas apuntan a GIBS', () => {
    const escena = escenaCaso('2017-01-26T23:30:00Z', ahora); // Las Máquinas, 26-ene-2017
    assert.equal(escena.key, 'viirs');
    assert.equal(escena.date, '2017-01-26');
    assert.ok(gibsTileUrl(escena.def, escena.date)[0].includes('/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/2017-01-26/'));
  });
});
