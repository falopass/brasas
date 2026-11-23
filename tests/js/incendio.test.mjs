/* Pruebas de las funciones puras de web/js/views/incendio.js con node:test (QA-101):
 * la ficha del incidente es la vista que se abre en plena emergencia. incidentInfo traduce
 * el estado a lo que se le dice a la persona, e incidentGeoJSON/incidentKML generan los
 * archivos que un brigadista o un periodista abre en QGIS o Google Earth (lon,lat, no lat,lon).
 * ui.js, importada en cadena, suscribe un listener «online» al cargar: se usa un stub mínimo. */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = { addEventListener() {} };
const { INCIDENT, atmosphereBlock, downwindBlock, incidentGeoJSON, incidentInfo, incidentKML, PARALLAX_NOTE, parallaxNote } = await import('../../web/js/views/incendio.js');

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

describe('parallaxNote', () => {
  test('solo aparece cuando hay GOES (ABI)', () => {
    assert.equal(parallaxNote(['VIIRS']), '');
    assert.equal(parallaxNote([]), '');
    assert.equal(parallaxNote(undefined), '');
  });
  test('con GOES dice la cifra medida y que la posición no se corrige', () => {
    const note = parallaxNote(['ABI', 'VIIRS']);
    assert.equal(note, PARALLAX_NOTE);
    assert.match(note, /1,6-3,0 km/);
    assert.match(note, /5,4 km/);
    assert.match(note, /sin corregir/);
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

describe('downwindBlock', () => {
  const ESCUELA = { name: 'Escuela Norte', distance_km: 1.5 };
  test('con viento nombra el rumbo', () => {
    const out = String(downwindBlock({ status: 'ok', wind_to: 'hacia el norte', items: [ESCUELA] }));
    assert.match(out, /Infraestructura sensible \(5 km\)/);
    assert.match(out, /hacia el norte: Escuela Norte \(1,5 km\)/);
  });
  test('sin viento no llama «a sotavento» a lo que está en todo el radio', () => {
    const out = String(downwindBlock({ status: 'ok', wind_to: null, items: [ESCUELA] }));
    assert.match(out, /Infraestructura sensible \(5 km\)/);
    assert.match(out, /Sin dirección de viento: Escuela Norte/);
    assert.doesNotMatch(out, /a sotavento|dirección del viento/);
  });
  test('con viento y sin elementos en el cono no niega los registros del radio', () => {
    const out = String(downwindBlock({ status: 'ok', wind_to: 'hacia el norte', items: [], total_radius: 2 }));
    assert.match(out, /Sin registros de OpenStreetMap en los 5 km a sotavento/);
  });
  test('sin viento y sin registros dice que no hay registros cercanos', () => {
    const out = String(downwindBlock({ status: 'ok', wind_to: null, items: [] }));
    assert.match(out, /Sin registros de OpenStreetMap en los 5 km/);
  });
  test('Overpass caído lo dice y no finge un cero', () => {
    const out = String(downwindBlock({ status: 'unavailable', items: [] }));
    assert.match(out, /OpenStreetMap no responde ahora/);
    assert.doesNotMatch(out, /Sin registros/);
  });
});

describe('atmosphereBlock', () => {
  const FULL_ATMOS = {
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

  test('con Haines alto marca callout-warn, usa dual y muestra fuente sin undefined ni NaN', () => {
    const out = String(atmosphereBlock(FULL_ATMOS));
    assert.match(out, /class="callout callout-warn"/);
    assert.match(out, /class="x-plain"/);
    assert.match(out, /class="x-tech"/);
    assert.match(out, /Haines 6\/6/);
    assert.match(out, /variante media/);
    assert.match(out, /850-700 hPa/);
    assert.match(out, /ΔT 12,4 °C/);
    assert.match(out, /T-Td 15,1 °C/);
    assert.match(out, /3,2 kPa/);
    assert.match(out, /0,08 m³\/m³/);
    assert.match(out, /0,12 m³\/m³/);
    assert.match(out, /8 % \(0–1 cm\)/);
    assert.match(out, /Inestabilidad para tormentas: baja/);
    assert.match(out, /el fuego podría crecer: alto/);
    assert.match(out, /450 J\/kg/);
    assert.match(out, /pico previsto/);
    assert.match(out, /hora de Chile continental/);
    assert.match(out, /consultado/);
    assert.match(out, /Pronóstico de modelo/);
    assert.ok(out.includes('href="https://open-meteo.com/en/docs"'));
    assert.ok(out.includes('target="_blank"') && out.includes('rel="noopener"'));
    assert.ok(out.includes('Open-Meteo · ECMWF IFS'));
    assert.doesNotMatch(out, /\bundefined\b|\bNaN\b/);
  });

  test('con observed_at futuro y fetched_at anterior no dice «recién»', () => {
    const future = new Date(Date.now() + 3 * 3600 * 1000).toISOString();
    const past = new Date(Date.now() - 25 * 60 * 1000).toISOString();
    const out = String(atmosphereBlock({ ...FULL_ATMOS, observed_at: future, fetched_at: past }));
    assert.match(out, /pico previsto/);
    assert.match(out, /consultado hace 25 min/);
    assert.doesNotMatch(out, /recién/);
  });

  test('con Haines bajo y VPD bajo no lleva callout-warn', () => {
    const out = String(atmosphereBlock({
      haines: { index: 3, level: 'muy_bajo', variant: 'baja', levels_hpa: '950-850' },
      vpd_kpa: 1.1,
      fetched_at: '2026-11-23T15:00:00Z',
    }));
    assert.match(out, /class="callout"/);
    assert.doesNotMatch(out, /callout-warn/);
    assert.match(out, /muy bajo/);
    assert.match(out, /3\/6/);
    assert.match(out, /1,1 kPa/);
    assert.doesNotMatch(out, /\bundefined\b|\bNaN\b/);
  });

  test('solo VPD sin Haines pinta el bloque, avisa si >= 3 kPa y no inventa campos', () => {
    const out = String(atmosphereBlock({
      haines: null,
      vpd_kpa: 3.1,
      soil_moisture_0_to_1cm: null,
      soil_moisture_0_to_7cm: null,
      cape_j_kg: null,
      observed_at: '2026-11-23T18:00:00Z',
    }));
    assert.match(out, /callout-warn/);
    assert.match(out, /3,1 kPa/);
    assert.doesNotMatch(out, /Haines|Suelo|CAPE/);
    assert.doesNotMatch(out, /\bundefined\b|\bNaN\b/);
  });

  test('sin objeto o sin ningún dato numérico válido devuelve cadena vacía', () => {
    assert.equal(atmosphereBlock(null), '');
    assert.equal(atmosphereBlock(undefined), '');
    assert.equal(atmosphereBlock({}), '');
    assert.equal(atmosphereBlock({
      haines: { index: null },
      vpd_kpa: null,
      soil_moisture_0_to_1cm: Number.NaN,
      soil_moisture_0_to_7cm: undefined,
      cape_j_kg: null,
    }), '');
  });
});
