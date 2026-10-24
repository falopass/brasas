/* Pruebas de los constructores de GeoJSON de web/js/map.js, con node:test y sin navegador. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { AGE_BINS, BASEMAPS, baseStyle, detectionsGeoJSON, placesGeoJSON, pointsGeoJSON } from '../../web/js/map.js';

// Haversine reimplementado acá (independiente de util.js) para validar circlePolygon sin circularidad.
function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const a = Math.sin(toRad(lat2 - lat1) / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(toRad(lon2 - lon1) / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(a));
}

// Mismo paso que la expresión AGE_COLOR del estilo: <1 h, <6 h, <24 h, el resto.
const ageBucket = (ageH) => AGE_BINS.findIndex((b) => ageH < b.maxH);

/* MAPA-105: las capas base deben ser de licencia abierta y con crédito visible.
   Esta guarda falla si una base pierde su atribución o deja de citar su licencia. */
describe('capas base: fuente abierta y crédito declarado', () => {
  test('la base vectorial (la por defecto) cita OpenFreeMap, OpenMapTiles y OpenStreetMap contributors', () => {
    for (const theme of ['light', 'dark']) {
      const style = baseStyle(theme, 'mapa');
      const attr = style.sources.omt.attribution;
      assert.match(attr, /OpenFreeMap/);
      assert.match(attr, /OpenMapTiles/);
      assert.match(attr, /© <a[^>]*openstreetmap\.org\/copyright[^>]*>OpenStreetMap contributors<\/a>/, `atribución ${theme}`);
    }
  });

  test('cada base del selector declara su crédito con su licencia', () => {
    assert.deepEqual(Object.keys(BASEMAPS), ['mapa', 'satelite', 'topo']);
    for (const [key, b] of Object.entries(BASEMAPS)) {
      if (!b.tiles) continue; // «mapa» se revisa arriba: su atribución vive en la fuente vectorial
      assert.ok(b.attribution && b.attribution.includes('<a'), `BASEMAPS.${key} sin crédito enlazado`);
      assert.match(b.attribution, /CC[ -]BY|Sentinel/, `BASEMAPS.${key} sin su licencia declarada`);
    }
    assert.match(BASEMAPS.topo.attribution, /CC-BY-SA/);
    assert.match(BASEMAPS.topo.attribution, /© <a[^>]*openstreetmap\.org\/copyright[^>]*>OpenStreetMap contributors<\/a>/);
    // La satelital de EOX usa el vintage 2017, licencia abierta CC BY 4.0 (NEG-05 resuelto).
    assert.match(BASEMAPS.satelite.attribution, /CC BY 4\.0/);
    assert.doesNotMatch(BASEMAPS.satelite.attribution, /NC-SA/);
  });
});

describe('detectionsGeoJSON', () => {
  const now = Date.parse('2026-03-01T12:00:00Z');
  const foco = (over) => ({
    id: 'f1', lon: -71.65, lat: -35.43, observed_at: '2026-03-01T11:30:00Z',
    frp_mw: 40, sensor: 'VIIRS', confidence: 'alta', ...over,
  });

  test('la edad cae en el bucket correcto y un punto sin fecha no revienta', () => {
    const { dots } = detectionsGeoJSON([
      foco({ id: 'reciente', observed_at: '2026-03-01T11:00:00Z' }),   // 1 h
      foco({ id: 'viejo', observed_at: '2026-02-28T06:00:00Z' }),      // 30 h
      foco({ id: 'sinfecha', observed_at: undefined }),                // age NaN
    ], now);
    assert.equal(dots.features.length, 3);
    const [a, b, c] = dots.features.map((f) => f.properties.age_h);
    assert.equal(a, 1);
    assert.equal(b, 30);
    assert.ok(Number.isNaN(c));
    assert.notEqual(ageBucket(a), ageBucket(b));
    assert.equal(AGE_BINS[ageBucket(a)].color, '#ff7a2e');
    assert.equal(AGE_BINS[ageBucket(b)].color, '#ffd38f');
  });

  test('frp_mw llega a las propiedades que alimentan el radio del estilo', () => {
    const { dots } = detectionsGeoJSON([foco({ frp_mw: 5 }), foco({ frp_mw: 500 })], now);
    assert.equal(dots.features[0].properties.frp_mw, 5);
    assert.equal(dots.features[1].properties.frp_mw, 500);
    assert.ok(dots.features[1].properties.frp_mw > dots.features[0].properties.frp_mw);
  });

  test('un punto por feature en dots; squares solo para ABI', () => {
    const pts = [foco({ sensor: 'VIIRS' }), foco({ id: 'abi', sensor: 'ABI' }), foco({ id: 'modis', sensor: 'MODIS' })];
    const { dots, squares } = detectionsGeoJSON(pts, now);
    assert.equal(dots.type, 'FeatureCollection');
    assert.equal(dots.features.length, pts.length);
    assert.equal(squares.features.length, 1);
    assert.equal(squares.features[0].properties.id, 'abi');
    assert.equal(squares.features[0].geometry.type, 'Polygon');
    assert.deepEqual(dots.features[0].geometry, { type: 'Point', coordinates: [-71.65, -35.43] });
  });

  test('confidence marca reliable solo en alta/nominal/media', () => {
    const { dots } = detectionsGeoJSON([foco({ confidence: 'alta' }), foco({ id: 'baja', confidence: 'baja' })], now);
    assert.equal(dots.features[0].properties.reliable, true);
    assert.equal(dots.features[1].properties.reliable, false);
  });
});

describe('placesGeoJSON', () => {
  const lugar = { id: 'casa', name: 'Casa', lon: -71.65, lat: -35.43, radius_km: 10 };

  test('el radio es un polígono cerrado a ~radius_km del centro', () => {
    const { points, radius } = placesGeoJSON([lugar]);
    assert.equal(points.features.length, 1);
    assert.deepEqual(points.features[0].geometry.coordinates, [-71.65, -35.43]);
    assert.equal(points.features[0].properties.id, 'casa');

    const ring = radius.features[0].geometry.coordinates[0];
    assert.equal(radius.features[0].geometry.type, 'Polygon');
    assert.equal(ring.length, 65);
    assert.deepEqual(ring[0], ring[ring.length - 1]);
    for (const [lon, lat] of ring) {
      const km = haversineKm(-35.43, -71.65, lat, lon);
      assert.ok(Math.abs(km - 10) <= 0.5, `vértice a ${km} km del centro`);
    }
    assert.equal(radius.features[0].properties.id, 'casa');
  });

  test('lista vacía devuelve colecciones vacías', () => {
    const { points, radius } = placesGeoJSON([]);
    assert.equal(points.type, 'FeatureCollection');
    assert.equal(radius.type, 'FeatureCollection');
    assert.equal(points.features.length, 0);
    assert.equal(radius.features.length, 0);
  });
});

describe('pointsGeoJSON', () => {
  const items = [
    { id: 'a', lon: -70.6, lat: -33.4, n: 1 },
    { id: 'b', lon: -71.6, lat: -35.4, n: 2 },
  ];

  test('respeta propsFn', () => {
    const fc = pointsGeoJSON(items, (i) => ({ etiqueta: `p-${i.id}`, n: i.n * 10 }));
    assert.equal(fc.type, 'FeatureCollection');
    assert.equal(fc.features.length, 2);
    assert.deepEqual(fc.features[0].properties, { etiqueta: 'p-a', n: 10 });
    assert.deepEqual(fc.features[1].properties, { etiqueta: 'p-b', n: 20 });
  });

  test('por defecto las propiedades son el ítem y la geometría va lon,lat', () => {
    const fc = pointsGeoJSON(items);
    assert.deepEqual(fc.features[0].properties, items[0]);
    assert.deepEqual(fc.features[0].geometry, { type: 'Point', coordinates: [-70.6, -33.4] });
  });
});
