/* Pruebas de las funciones puras de web/js/views/incendio.js con node:test (QA-101):
 * la ficha del incidente es la vista que se abre en plena emergencia. incidentInfo traduce
 * el estado a lo que se le dice a la persona, e incidentGeoJSON/incidentKML generan los
 * archivos que un brigadista o un periodista abre en QGIS o Google Earth (lon,lat, no lat,lon).
 * ui.js, importada en cadena, suscribe un listener «online» al cargar: se usa un stub mínimo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = { addEventListener() {} };
const { INCIDENT, incidentGeoJSON, incidentInfo, incidentKML } = await import('../../web/js/views/incendio.js');

const INC = { id: 'inc-abc', status: 'posible', lat: -36.62, lon: -72.11, comuna: 'Quillón', region: 'Ñuble' };
const EVIDENCE = [
  { lon: -72.1, lat: -36.6, observed_at: '2026-10-20T18:00:00Z', sensor: 'VIIRS', satellite: 'NOAA-21', confidence: 'nominal', frp_mw: 12.5, source: 'firms' },
];
const DATA = (inc = {}, extra = {}) => ({ incident: { ...INC, ...inc }, evidence: EVIDENCE, timeline: null, ...extra });

describe('incidentInfo', () => {
  test('cada estado del mapa INCIDENT devuelve tono, título, resumen y definición técnica', () => {
    for (const [status, info] of Object.entries(INCIDENT)) {
      const got = incidentInfo({ status });
      assert.equal(got, info, status);
      for (const key of ['tone', 'short', 'title', 'text', 'tech']) assert.ok(got[key], `${status}.${key}`);
    }
  });
  test('reportado y confirmado son tono urgente y nombran su evidencia', () => {
    assert.equal(incidentInfo({ status: 'reportado' }).tone, 'urgente');
    assert.match(incidentInfo({ status: 'reportado' }).text, /vecino/i);
    const conf = incidentInfo({ status: 'confirmado' });
    assert.equal(conf.tone, 'urgente');
    assert.match(conf.text, /CONAF/);
    assert.match(conf.text, /SENAPRED/);
  });
  test('controlado es aviso y extinguido es tranquilo, sin prometer «apagado»', () => {
    assert.equal(incidentInfo({ status: 'controlado' }).tone, 'aviso');
    const ext = incidentInfo({ status: 'extinguido' });
    assert.equal(ext.tone, 'tranquilo');
    assert.match(ext.text, /No significa «apagado oficialmente»/);
  });
  test('una fuente fija (volcán, industria) no se lee como incendio, pese al estado', () => {
    const info = incidentInfo({ status: 'confirmado', fixed_source: true });
    assert.equal(info.tone, 'tranquilo');
    assert.equal(info.short, 'Fuente fija');
    assert.doesNotMatch(`${info.title} ${info.text}`, /incendio/i);
  });
  test('un estado desconocido cae en la rama anomalia, no revienta', () => {
    assert.equal(incidentInfo({ status: 'inventado' }), INCIDENT.anomalia);
    assert.equal(incidentInfo({}), INCIDENT.anomalia);
  });
  test('descartado (fuera de Chile) no se lee como una señal de calor', () => {
    const info = incidentInfo({ status: 'descartado' });
    assert.equal(info.tone, 'tranquilo');
    assert.doesNotMatch(`${info.title} ${info.text}`, /señal de calor|satélite vio calor/i);
    assert.match(info.text, /no lo cuenta como incendio de Chile/i);
    assert.match(info.tech, /comuna chilena/i);
  });
});

describe('incidentGeoJSON', () => {
  test('FeatureCollection con Features Point y coordenadas en orden [lon, lat]', () => {
    const gj = incidentGeoJSON(DATA());
    assert.equal(gj.type, 'FeatureCollection');
    assert.equal(gj.features.length, EVIDENCE.length + 1);
    for (const f of gj.features) {
      assert.equal(f.type, 'Feature');
      assert.equal(f.geometry.type, 'Point');
    }
    assert.deepEqual(gj.features[0].geometry.coordinates, [-72.1, -36.6], 'detección: [lon, lat]');
    assert.deepEqual(gj.features.at(-1).geometry.coordinates, [-72.11, -36.62], 'centro: [lon, lat]');
  });
  test('cada feature lleva el id y el estado del incidente', () => {
    for (const f of incidentGeoJSON(DATA()).features) {
      assert.equal(f.properties.incidente, 'inc-abc');
      assert.equal(f.properties.estado, 'posible');
    }
  });
  test('las detecciones se distinguen del centro y conservan sensor, hora y confianza', () => {
    const [det, centro] = incidentGeoJSON(DATA()).features;
    assert.equal(det.properties.tipo, 'deteccion');
    assert.equal(det.properties.sensor, 'VIIRS');
    assert.equal(det.properties.hora, '2026-10-20T18:00:00Z');
    assert.equal(det.properties.confianza, 'nominal');
    assert.equal(centro.properties.tipo, 'centro');
  });
  test('la última huella del timeline se agrega como feature «huella»', () => {
    const poly = { type: 'Polygon', coordinates: [[[-72.2, -36.7], [-72.0, -36.7], [-72.0, -36.5], [-72.2, -36.5], [-72.2, -36.7]]] };
    const gj = incidentGeoJSON(DATA({}, { timeline: { hours: [], frames: [{ t: 't', geometry: poly }], footprint_note: 'n' } }));
    const fp = gj.features.at(-1);
    assert.equal(fp.properties.tipo, 'huella');
    assert.equal(fp.geometry.type, 'Polygon');
    assert.deepEqual(fp.geometry.coordinates[0][0], [-72.2, -36.7]);
  });
});

describe('incidentKML', () => {
  test('documento KML con un Placemark por detección y uno para el centro', () => {
    const kml = incidentKML(DATA());
    assert.match(kml, /^<\?xml version="1\.0" encoding="UTF-8"\?>/);
    assert.ok(kml.includes('<kml xmlns="http://www.opengis.net/kml/2.2">'));
    assert.equal((kml.match(/<Placemark>/g) || []).length, EVIDENCE.length + 1);
    assert.ok(kml.includes('<name>Centro del incidente</name>'));
  });
  test('las coordenadas van en formato KML lon,lat,0', () => {
    const kml = incidentKML(DATA());
    assert.ok(kml.includes('<Point><coordinates>-72.1,-36.6,0</coordinates></Point>'), 'detección');
    assert.ok(kml.includes('<Point><coordinates>-72.11,-36.62,0</coordinates></Point>'), 'centro');
  });
  test('el nombre y la descripción escapan & y <', () => {
    const kml = incidentKML(DATA({ id: 'a<&b' }));
    assert.ok(kml.includes('<name>BRASA · incendio a&lt;&amp;b</name>'));
    assert.ok(!kml.includes('a<&b'), 'el id no entra crudo al XML');
  });
  test('la huella se serializa como Polygon con anillo lon,lat,0', () => {
    const poly = { type: 'Polygon', coordinates: [[[-72.2, -36.7], [-72.0, -36.7], [-72.0, -36.5], [-72.2, -36.7]]] };
    const kml = incidentKML(DATA({}, { timeline: { hours: [], frames: [{ t: 't', geometry: poly }] } }));
    assert.ok(kml.includes('<Polygon><outerBoundaryIs><LinearRing>'));
    assert.ok(kml.includes('<coordinates>-72.2,-36.7,0 -72,-36.7,0 -72,-36.5,0 -72.2,-36.7,0</coordinates>'));
  });
});

describe('incidente sin comuna', () => {
  test('no rompe la generación de GeoJSON ni de KML', () => {
    const { comuna, region, ...sinComuna } = INC;
    const data = DATA(sinComuna);
    assert.equal(incidentGeoJSON(data).type, 'FeatureCollection');
    assert.ok(incidentKML(data).includes('<Placemark>'));
  });
});
