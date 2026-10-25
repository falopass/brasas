/* Ficha de un incidente en vivo: la evidencia satelital agrupada, su estado en palabras sencillas,
 * la línea de tiempo (qué vio cada satélite y cuándo) y la reproducción hora a hora de la huella.
 * Usa el mismo motor que los casos históricos (backend/cases.py) y nunca se presenta como fuente oficial. */
import { api, request } from '../api.js';
import { timeChart } from '../charts.js';
import { errorConSalida } from '../errores.js';
import { fitBbox, getMap, onReady, setData, show } from '../map.js';
import { spreadWords } from '../spreadtext.js';
import { store } from '../store.js';
import { placeForm, reportForm } from '../ui.js';
import { $, ago, bearingDeg, cardinal, download, dual, emberSvg, escapeHtml, fmtDateTime, fmtNum, fmtUTC, haversineKm, html, keepPlace, minutesSince, nearestPlacesText, parseUTC, pixelSquare, relativeToWind, SENSOR_LABEL, toast, TZ } from '../util.js';

const EMPTY = { type: 'FeatureCollection', features: [] };
const LAYERS = ['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'official-perimeter-fill', 'official-perimeter-line'];
const REFRESH_MS = 3 * 60 * 1000;

/** Cada estado: tono visual, título y explicación para cualquier persona; la definición exacta, para la lectura detallada. */
export const INCIDENT = {
  anomalia: { tone: 'aviso', short: 'Señal de calor', title: 'Una señal de calor', text: 'Un satélite vio calor una vez. Puede ser un incendio, una quema o una industria: aún no hay más pruebas.', tech: 'Anomalía: una sola detección confiable o solo detecciones de confianza baja.' },
  posible: { tone: 'riesgo', short: 'Posible incendio', title: 'Posible incendio', text: 'Los satélites vieron calor en el mismo lugar más de una vez, o dos satélites distintos lo vieron. Es probable que sea fuego.', tech: 'Posible: ≥ 2 detecciones confiables en momentos distintos, o 2 sensores distintos (p. ej. GOES + VIIRS).' },
  reportado: { tone: 'urgente', short: 'Visto por vecinos', title: 'Posible incendio, también visto por vecinos', text: 'Además del satélite, un vecino avisó de fuego o humo cerca y BRASA revisó su aviso.', tech: 'Reportado: evidencia satelital + reporte ciudadano verificado por moderación a ≤ 3 km.' },
  confirmado: { tone: 'urgente', short: 'Confirmado por CONAF', title: 'Incendio informado por CONAF', text: 'CONAF informa este incendio. Sigue las instrucciones de SENAPRED y de la autoridad local.', tech: 'Confirmado: unido a un incendio del reporte público de CONAF a ≤ 3 km. BRASA no confirma por su cuenta.' },
  controlado: { tone: 'aviso', short: 'Controlado', title: 'Controlado según CONAF', text: 'CONAF lo informa como controlado. Aún puede haber humo o rebrotes.', tech: 'Controlado: según el reporte público de CONAF.' },
  extinguido: { tone: 'tranquilo', short: 'Sin calor nuevo', title: 'Sin calor nuevo', text: 'Los satélites no ven calor aquí hace más de un día. No significa «apagado oficialmente», salvo que CONAF lo informe.', tech: 'Extinguido: 24 h sin detecciones nuevas, o extinguido según CONAF si está unido a su reporte.' },
  descartado: { tone: 'tranquilo', short: 'Descartado', title: 'Punto descartado', text: 'BRASA no lo cuenta como incendio de Chile ni avisa por él.', tech: 'Descartado: el incidente quedó sin comuna chilena —sus detecciones cayeron fuera del país—; la fila se conserva para auditoría y sale con la purga normal.' },
};
const FIXED = { tone: 'tranquilo', short: 'Fuente fija', title: 'Calor de una fuente fija', text: 'Este calor aparece siempre en el mismo lugar (un volcán o una industria). Por eso BRASA no avisa por él.', tech: 'Fuente fija probable: toda la evidencia cae en un volcán activo o en una celda con calor ≥ 8 días de los últimos 30.' };

export const incidentInfo = (inc) => (inc.fixed_source ? FIXED : INCIDENT[inc.status] || INCIDENT.anomalia);

/** GOES no corrige el relieve (INV-05): la ficha lo dice con la cifra medida, sin mover el punto. */
export const PARALLAX_NOTE = 'La posición de los focos GOES no corrige el relieve: a 2.000-3.000 m el punto puede estar corrido 1,6-3,0 km en Chile central y hasta 5,4 km en Magallanes. Se publica sin corregir.';
export const parallaxNote = (sensors) => ((sensors || []).includes('ABI') ? PARALLAX_NOTE : '');

let mounted = false;
let S = null;
let timer = null;
let seq = 0;

/** Texto listo para compartir la ficha: el enlace y el recordatorio de que no es una alerta oficial.
 *  El enlace es /i/<id> y no el #/: los rastreadores (WhatsApp, Telegram) no ven el fragmento y
 *  sin esa ruta la vista previa saldría con la tarjeta genérica del sitio (UX-05). */
const shareText = (inc, info, where) => {
  const url = `${location.origin}/i/${inc.id}`;
  return { title: `BRASA · ${info.title}`,
    text: `«${info.title}» en ${where} — mira la ficha en BRASA: ${url} · No es una alerta oficial: sigue a SENAPRED (senapred.cl).` };
};

const sensorWord = (s) => (s === 'ABI' ? 'el satélite que mira cada 10 min' : 'un satélite de paso');
const confWord = (c) => ({ alta: 'alta', nominal: 'normal', media: 'media', baja: 'baja' }[c] || 'sin dato');

const listEs = (items) => (items.length > 1 ? `${items.slice(0, -1).join(', ')} y ${items.at(-1)}` : items[0] || '');
/** «A 8 km de «Casa»», con los demás lugares cercanos si los hay; `digits` ajusta el detalle del número. */
const placesLine = (np, digits) => {
  const item = (e) => `${fmtNum(e.km, digits(e.km))} km de «${e.name}»`;
  return `A ${item(np.nearest)}${np.others.length ? `. También ${listEs(np.others.map((e) => `a ${item(e)}`))}` : ''}.`;
};

/** «¿Viene hacia mi casa?» (FUEGO-17): el viento del escenario contra cada lugar que ya
 *  se muestra. El viento del API indica de dónde viene; el fuego avanza hacia donde sopla.
 *  Devuelve { plain, tech } para `dual()`, o null si no hay viento o no hay lugares. */
const windLine = (inc, np, spread) => {
  const deg = spread?.wind_deg;
  // Con viento en calma la dirección no dice nada: mismo umbral que radarSvg.
  if (!np || !Number.isFinite(deg) || !(Number(spread?.wind_kmh) > 1)) return null;
  const FRASE = {
    hacia: (n) => `eso podría empujar el fuego hacia «${n}»`,
    'en contra': (n) => `eso podría alejar el fuego de «${n}»`,
    'de costado': (n) => `el fuego podría pasar de costado a «${n}»`,
  };
  const grados = (x) => Math.round(x) % 360;
  const items = [np.nearest, ...np.others].map((p) => {
    const rumbo = bearingDeg(inc.lat, inc.lon, p.lat, p.lon);
    return { name: p.name, rumbo, rel: relativeToWind(rumbo, deg) };
  }).filter((p) => p.rel);
  if (!items.length) return null;
  const plain = `El viento de ahora sopla hacia el ${cardinal(deg + 180)}: ${listEs(items.map((p) => FRASE[p.rel.estado](p.name)))} (escenario estimado: no es una predicción).`;
  const tech = `Viento ${fmtNum(spread.wind_kmh, 0)} km/h desde ${grados(deg)}° (${cardinal(deg)}), sopla hacia ${grados(deg + 180)}° · ${items.map((p) => `«${p.name}» a rumbo ${grados(p.rumbo)}°: ${p.rel.estado} (Δ ${p.rel.angulo}°)`).join(' · ')}`;
  return { plain, tech };
};

const AVISO = 'BRASA no es fuente oficial: un incidente agrupa detecciones satelitales y puede ser un incendio, una quema o una industria. Sigue a SENAPRED y CONAF.';

/** La geometría de la última huella del timeline, si existe. */
const lastFootprint = (data) => data.timeline?.frames?.at(-1)?.geometry || null;

/** Caja [oeste, sur, este, norte] de una geometría GeoJSON (Polygon o MultiPolygon). */
const geomBbox = (geometry) => {
  const flat = (c) => (typeof c[0] === 'number' ? [c] : c.flatMap(flat));
  let w = Infinity; let s = Infinity; let e = -Infinity; let n = -Infinity;
  for (const [lon, lat] of flat(geometry?.coordinates || [])) {
    if (lon < w) w = lon; if (lon > e) e = lon;
    if (lat < s) s = lat; if (lat > n) n = lat;
  }
  return Number.isFinite(w) ? [w, s, e, n] : null;
};
const bboxUnion = (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])];

/** Los mismos datos de la ficha como GeoJSON, para brigadistas y análisis técnico. */
export function incidentGeoJSON(data) {
  const inc = data.incident;
  const common = { incidente: inc.id, estado: inc.status, aviso: AVISO, descargado: new Date().toISOString() };
  const features = data.evidence.map((e) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [e.lon, e.lat] },
    properties: { ...common, tipo: 'deteccion', hora: e.observed_at, sensor: e.sensor, satelite: e.satellite || null,
      confianza: e.confidence || null, frp_mw: e.frp_mw ?? null, fuente: e.source || null } }));
  features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [inc.lon, inc.lat] }, properties: { ...common, tipo: 'centro' } });
  const footprint = lastFootprint(data);
  if (footprint) features.push({ type: 'Feature', geometry: footprint, properties: { ...common, tipo: 'huella', nota: data.timeline.footprint_note } });
  return { type: 'FeatureCollection', features };
}

const kmlCoord = ([lon, lat]) => `${lon},${lat},0`;
const ring = (coords) => coords.map(kmlCoord).join(' ');

/** El mismo contenido como KML: un Placemark por detección, el centro y la huella como polígono. */
export function incidentKML(data) {
  const inc = data.incident;
  const doc = `BRASA · incidente ${inc.id} · descargado ${new Date().toISOString()} · ${AVISO}`;
  const places = data.evidence.map((e) => `<Placemark><name>Detección ${escapeHtml(e.observed_at)}</name>`
    + `<description>${escapeHtml(`${e.sensor || ''} ${e.satellite || ''} · conf. ${e.confidence || 'n/d'} · FRP ${e.frp_mw ?? 'n/d'} MW`.trim())}</description>`
    + `<Point><coordinates>${kmlCoord([e.lon, e.lat])}</coordinates></Point></Placemark>`);
  places.push(`<Placemark><name>Centro del incidente</name><Point><coordinates>${kmlCoord([inc.lon, inc.lat])}</coordinates></Point></Placemark>`);
  const footprint = lastFootprint(data);
  if (footprint) {
    const polys = footprint.type === 'Polygon' ? [footprint.coordinates] : footprint.type === 'MultiPolygon' ? footprint.coordinates : [];
    for (const rings of polys) {
      places.push(`<Placemark><name>Huella aproximada</name><Polygon><outerBoundaryIs><LinearRing><coordinates>${ring(rings[0])}</coordinates></LinearRing></outerBoundaryIs>${
        rings.slice(1).map((r) => `<innerBoundaryIs><LinearRing><coordinates>${ring(r)}</coordinates></LinearRing></innerBoundaryIs>`).join('')}</Polygon></Placemark>`);
    }
  }
  return `<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>BRASA · incendio ${escapeHtml(inc.id)}</name><description>${escapeHtml(doc)}</description>${places.join('')}</Document></kml>`;
}

// ---------------------------------------------------------------- avance por hora (MAPA-156)
// La huella acumulada de cada frame como banda —tenue la más antigua, intensa la más
// reciente— y una flecha del desplazamiento centroide→centroide entre la primera y la
// última hora con dato. Las capas se agregan en tiempo de ejecución sobre el estilo
// vigente (map.js no las declara entre sus overlays) y se reponen en cada `style.load`:
// cambiar el tema o el mapa base borra todo lo que no es del estilo.
const BAND_SOURCE = 'case-hours';
const ARROW_SOURCE = 'case-hours-dir';
const BAND_LAYERS = ['case-hours-fill', 'case-hours-arrow', 'case-hours-arrow-label'];
const MIN_SHIFT_KM = 2; // el píxel efectivo de GOES en Chile (~2-3 km): menos que eso es ruido, no avance

/** Centroide de un Polygon/MultiPolygon GeoJSON: vértices ponderados por el área firmada
 *  de cada anillo (los huecos restan solos si vienen con la orientación inversa). */
export function geomCentroid(geometry) {
  const rings = geometry?.type === 'Polygon' ? geometry.coordinates
    : geometry?.type === 'MultiPolygon' ? geometry.coordinates.flat() : null;
  let a = 0; let x = 0; let y = 0;
  for (const ring of rings || []) {
    for (let i = 0; i < ring.length - 1; i++) {
      const w = ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
      a += w; x += (ring[i][0] + ring[i + 1][0]) * w; y += (ring[i][1] + ring[i + 1][1]) * w;
    }
  }
  if (a) return [x / (3 * a), y / (3 * a)];
  const pts = (rings || []).flat(); // geometría degenerada: promedio simple de vértices
  return pts.length ? [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length] : null;
}

/** Punto a `km` de (lon, lat) en dirección `deg` desde el norte; el mismo plano local de circlePolygon. */
const destKm = (lon, lat, deg, km) => [
  lon + (km * Math.sin((deg * Math.PI) / 180)) / (111.32 * Math.cos((lat * Math.PI) / 180)),
  lat + (km * Math.cos((deg * Math.PI) / 180)) / 110.574,
];

/** Las bandas del avance: un feature por frame con `frac` (0 = primera hora con dato,
 *  1 = la última) para el color y `ord` para el orden de dibujo. Las huellas son
 *  acumuladas —cada frame contiene al anterior—, así que la más antigua va arriba:
 *  lo que se ve en cada punto es la hora en que el calor llegó ahí. */
export function bandsGeoJSON(frames = []) {
  const n = frames.length;
  const features = [];
  frames.forEach((f, i) => {
    if (f?.geometry) features.push({ type: 'Feature', geometry: f.geometry, properties: { frac: n > 1 ? i / (n - 1) : 1, ord: n - 1 - i } });
  });
  return { type: 'FeatureCollection', features: features.reverse() };
}

/** La flecha del desplazamiento observado: centroide de la primera huella al de la última,
 *  con su rótulo. null si hay menos de dos horas con dato o si el desplazamiento no supera
 *  el tamaño de un píxel GOES (~2 km). */
export function arrowGeoJSON(frames = []) {
  if (frames.length < 2) return null;
  const a = geomCentroid(frames[0].geometry); const b = geomCentroid(frames.at(-1).geometry);
  if (!a || !b) return null;
  const km = haversineKm(a[1], a[0], b[1], b[0]);
  if (km < MIN_SHIFT_KM) return null;
  const dir = bearingDeg(a[1], a[0], b[1], b[0]);
  const head = Math.min(4, Math.max(0.6, km * 0.25));
  const lines = [[a, b], [b, destKm(b[0], b[1], dir + 150, head)], [b, destKm(b[0], b[1], dir + 210, head)]];
  return { type: 'FeatureCollection', features: [
    { type: 'Feature', geometry: { type: 'MultiLineString', coordinates: lines }, properties: {} },
    { type: 'Feature', geometry: { type: 'Point', coordinates: destKm(a[0], a[1], dir, km * 0.5) }, properties: { label: 'dirección observada · estimación' } },
  ] };
}

/** Crea las fuentes y capas del avance si el estilo vigente aún no las tiene y deja
 *  los datos y la visibilidad al día. Corre también al recargarse el estilo. */
function paintAvance() {
  const map = getMap();
  if (!map || !mounted || !S) return;
  if (!map.isStyleLoaded() || !map.getSource('case-footprint')) { onReady(paintAvance); return; }
  if (!map.getSource(BAND_SOURCE)) map.addSource(BAND_SOURCE, { type: 'geojson', data: EMPTY });
  if (!map.getSource(ARROW_SOURCE)) map.addSource(ARROW_SOURCE, { type: 'geojson', data: EMPTY });
  const dark = store.get('theme') === 'dark';
  const ink = dark ? '#e8e2d4' : '#3a3530';
  const ramp = ['interpolate', ['linear'], ['get', 'frac'], 0, '#ffd38f', 0.6, '#ff7a2e', 1, '#ff4b1f'];
  if (!map.getLayer(BAND_LAYERS[0])) {
    map.addLayer({ id: BAND_LAYERS[0], type: 'fill', source: BAND_SOURCE,
      layout: { 'fill-sort-key': ['get', 'ord'] },
      paint: { 'fill-color': ramp, 'fill-opacity': 0.5, 'fill-outline-color': ramp } },
      map.getLayer('case-footprint-fill') ? 'case-footprint-fill' : undefined);
  }
  if (!map.getLayer(BAND_LAYERS[1])) map.addLayer({ id: BAND_LAYERS[1], type: 'line', source: ARROW_SOURCE, paint: { 'line-color': ink, 'line-width': 2.4, 'line-opacity': 0.9 } });
  if (!map.getLayer(BAND_LAYERS[2])) {
    map.addLayer({ id: BAND_LAYERS[2], type: 'symbol', source: ARROW_SOURCE,
      layout: { 'symbol-placement': 'point', 'text-field': ['coalesce', ['get', 'label'], ''], 'text-font': ['Noto Sans Regular'], 'text-size': 11, 'text-offset': [0, 0.9], 'text-allow-overlap': true },
      paint: { 'text-color': ink, 'text-halo-color': dark ? '#100f0d' : '#efe9df', 'text-halo-width': 1.4 } });
  }
  map.getSource(BAND_SOURCE).setData(S.bands || EMPTY);
  map.getSource(ARROW_SOURCE).setData(S.arrow || EMPTY);
  for (const id of BAND_LAYERS) map.setLayoutProperty(id, 'visibility', S.bands?.features.length && S.bandsOn ? 'visible' : 'none');
}
const onStyleLoad = () => paintAvance();

/** Leyenda corta del avance: solo cuando las bandas están visibles. */
function legendAvance() {
  $('#map-legend').innerHTML = S?.bands?.features.length && S.bandsOn ? String(html`<div class="legend-title">Avance por hora</div>
    <div class="legend-row"><span class="legend-item"><span class="sw sw-sq" style="background:#ffd38f"></span>${dual('Primera hora', 'más antigua')}</span>
      <span class="legend-item"><span class="sw sw-sq" style="background:#ff4b1f"></span>${dual('Última hora', 'más reciente')}</span></div>
    <div class="legend-note">${dual('Más intenso = más reciente. Es lo que vieron los satélites, no el frente del fuego.', 'Bandas: huella acumulada por hora. Flecha: desplazamiento centroide→centroide entre la primera y la última hora con dato.')}</div>`) : '';
}

function paint(index) {
  const hours = S.tl.hours;
  const end = parseUTC(hours[index].t).getTime() + 3600000;
  const goes = []; const dots = [];
  for (const e of S.evidence) {
    const t = parseUTC(e.observed_at).getTime();
    if (t >= end) continue;
    const age = (end - t) / 3600000;
    if (e.sensor === 'ABI') goes.push({ type: 'Feature', geometry: pixelSquare(e.lon, e.lat, 2.5), properties: { age_h: age } });
    else dots.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [e.lon, e.lat] }, properties: { age_h: age } });
  }
  let frame = null;
  for (const f of S.tl.frames) { if (parseUTC(f.t).getTime() <= end) frame = f; else break; }
  setData('case-goes', { type: 'FeatureCollection', features: goes });
  setData('case-points', { type: 'FeatureCollection', features: dots });
  setData('case-footprint', frame ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: frame.geometry, properties: {} }] } : EMPTY);
  const root = S.container;
  root.querySelector('#in-time').textContent = fmtDateTime(hours[index].t);
  const slider = root.querySelector('#in-slider');
  slider.value = String(index);
  slider.style.setProperty('--p', `${(100 * index) / Math.max(1, hours.length - 1)}%`);
  root.querySelector('#in-area').textContent = hours[index].footprint_ha ? `${fmtNum(hours[index].footprint_ha)} ha` : '—';
  S.chart?.setCursor(index);
  S.index = index;
}

function render(container, data, testigos, rayos) {
  const inc = data.incident;
  // La marca «hubo rayos cerca del inicio» (DET-03) viaja en el GeoJSON abierto de
  // incidentes, no en el detalle de la API: se busca el mismo incidente ahí.
  const rayo = (rayos?.features || []).find((f) => f.properties?.id === inc.id)?.properties || null;
  const info = incidentInfo(inc);
  const tl = data.timeline;
  const testigoRows = (testigos?.reports || []).slice(0, 5);
  const stale = data.data_as_of && minutesSince(data.data_as_of) > 30;
  const where = inc.comuna ? `${inc.comuna}, ${inc.region}` : 'Fuera del territorio chileno';
  const nearPlaces = nearestPlacesText(inc, store.get('places'));
  const recent = [...data.evidence].reverse().slice(0, 40);
  const latency = Object.entries(data.latency);
  const escenario = spreadWords(data.spread);
  const vientoLugares = windLine(inc, nearPlaces, data.spread);
  container.innerHTML = String(html`
    <a class="btn btn-sm btn-ghost" id="in-back" href="#/mapa">← Mapa</a>
    <div class="ember-hero st-${info.tone}" role="status" style="margin-top:10px">${emberSvg({ tone: info.tone })}
      <div><div class="hero-label">${info.title}</div>
        <small>${where}. ${dual(info.text, info.tech)}</small>
        ${inc.fixed_source && inc.fixed_reason ? html`<small class="tiny muted x-tech" style="display:block">Motivo: ${inc.fixed_reason}.</small>` : ''}
        ${['reportado', 'confirmado'].includes(inc.status) ? html`<div class="btn-row hero-cta"><a class="btn btn-sm btn-call" id="in-call" href="tel:132">Llamar a Bomberos · 132</a></div>` : ''}</div></div>
    ${stale ? html`<div class="callout callout-warn stale-note" role="alert"><b>Los datos de los satélites no se actualizan desde ${ago(data.data_as_of)}.</b> Que no veamos calor nuevo no significa que no lo haya.</div>` : ''}
    ${data.official_fire ? html`<div class="em-official"><b>CONAF informa: «${data.official_fire.name || 'sin nombre'}» · ${data.official_fire.status_raw}</b>
      <span>Empezó ${fmtDateTime(data.official_fire.started_at)}${data.official_fire.area_ha ? ` · ${fmtNum(data.official_fire.area_ha, data.official_fire.area_ha < 10 ? 1 : 0)} ha` : ''}${data.official_fire.controlled_at ? ` · controlado ${fmtDateTime(data.official_fire.controlled_at)}` : ''}${data.official_fire.extinguished_at ? ` · extinguido ${fmtDateTime(data.official_fire.extinguished_at)}` : ''}.</span>
      <span class="tiny">Fuente: <a href="${data.official_source.url}" target="_blank" rel="noopener">CONAF, reporte público de incendios</a>. BRASA unió este aviso oficial con lo que vieron los satélites a menos de 3 km.</span></div>` : ''}
    ${data.official_perimeter ? html`<p class="tiny muted x-tech" style="margin-top:6px">Perímetro oficial CONAF${data.official_perimeter.area_ha != null ? ` · ${fmtNum(data.official_perimeter.area_ha, 1)} ha` : ''}${data.official_perimeter.edited_at ? ` · ${parseUTC(data.official_perimeter.edited_at).toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: 'numeric', timeZone: TZ })}` : ''}.
      La línea a trazos del mapa es ese borde final; lo demás sigue siendo huella satelital aproximada.
      ${data.official_perimeter.source?.url ? html`Fuente: <a href="${data.official_perimeter.source.url}" target="_blank" rel="noopener">${data.official_perimeter.source.name}</a>.` : ''}</p>` : ''}
    ${data.protected_area ? html`<p class="small">${dual(
      data.protected_area.inside ? `Dentro de un área protegida del Estado: ${data.protected_area.name}.`
        : `A ${fmtNum(data.protected_area.distance_km, 1)} km de un área protegida: ${data.protected_area.name}.`,
      `${data.protected_area.category || 'Área protegida'} del SNASPE${data.protected_area.region ? ` · ${data.protected_area.region}` : ''} · ${data.protected_area.inside ? 'el punto está dentro del polígono' : `borde a ${fmtNum(data.protected_area.distance_km, 1)} km`}.`)}
      <span class="tiny muted">Área protegida: CONAF.</span></p>` : ''}
    <div class="kpis">
      <div class="kpi"><small>${dual('veces que se vio calor', 'detecciones')}</small><strong>${fmtNum(inc.n_obs)}</strong></div>
      <div class="kpi"><small>${dual('primera vez', 'primera detección')}</small><strong class="small-figure">${ago(inc.first_seen_at)}</strong></div>
      <div class="kpi"><small>${dual('última vez', 'última detección')}</small><strong class="small-figure">${ago(inc.last_seen_at)}</strong></div>
    </div>
    ${nearPlaces ? html`<p class="small">${dual(placesLine(nearPlaces, (km) => (km < 10 ? 1 : 0)), placesLine(nearPlaces, () => 1))}</p>` : ''}
    ${vientoLugares ? html`<p class="small">${dual(vientoLugares.plain, vientoLugares.tech)}</p>` : ''}
    <p class="small">${dual(`Lo vieron ${inc.sensors.length >= 2 ? 'dos tipos de satélite distintos' : sensorWord(inc.sensors[0])}. ${inc.n_reliable < inc.n_obs ? `${inc.n_obs - inc.n_reliable} de las señales son dudosas.` : ''}`,
      `Sensores: ${inc.sensors.map((s) => SENSOR_LABEL[s] || s).join(' + ')} · confiables ${inc.n_reliable}/${inc.n_obs} · FRP máx. ${inc.max_frp != null ? `${fmtNum(inc.max_frp, 1)} MW` : 'n/d'} · estado desde ${fmtDateTime(inc.status_changed_at)}.`)}</p>
    ${rayo?.lightning_km != null ? html`<p class="small">${dual(`Hubo rayos a ${fmtNum(rayo.lightning_km, 1)} km poco antes de la primera detección: un rayo cerca no prueba el origen.`,
      `GLM de GOES-19 (NOAA, dominio público): ${rayo.lightning_count ?? 1} destello${(rayo.lightning_count ?? 1) === 1 ? '' : 's'} sobre territorio chileno a ≤ 5 km en las 2 h previas a ${fmtUTC(inc.first_seen_at)}${rayo.lightning_last_at ? ` · último ${fmtUTC(rayo.lightning_last_at)}` : ''}.`)}</p>` : ''}
    ${parallaxNote(inc.sensors) ? html`<p class="small">${dual(parallaxNote(inc.sensors),
      'Paralaje GOES (INV-05): el producto FDC no corrige el relieve; a 3.000 m el píxel aparente se corre 2,45 km al sur en Santiago y 5,38 km en Punta Arenas. La posición publicada es la del producto, sin corregir.')}</p>` : ''}
    ${escenario ? html`<div class="callout"><b>${dual('Escenario estimado de avance', 'Escenario estimado de propagación')}.</b>
      <span style="display:block">${escenario.resumen}</span>
      <span class="small" style="display:block">${escenario.porque}</span>
      <span class="tiny muted" style="display:block">${escenario.etiqueta}</span>
      ${escenario.tecnico || data.spread.assumptions?.length ? html`<details class="fold fold-sm" style="margin-top:6px"><summary>Detalle técnico</summary><div>
        ${escenario.tecnico ? html`<p class="tiny muted x-tech" style="margin:0">${escenario.tecnico}</p>` : ''}
        ${data.spread.assumptions?.length ? html`<p class="tiny muted" style="margin:4px 0 0">Supuestos: ${data.spread.assumptions.join(' ')}</p>` : ''}
      </div></details>` : ''}</div>` : ''}
    <div class="btn-row"><button class="btn btn-primary" id="in-watch">Avisarme si crece</button><button class="btn btn-ghost" id="in-report">Contar lo que veo</button><button class="btn btn-ghost" id="in-share">Compartir</button></div>
    <div class="x-tech" style="margin-top:10px">
      <p class="small muted">Descarga técnica: los mismos datos de esta ficha, para brigadistas y análisis técnico.</p>
      <div class="btn-row"><button class="btn btn-sm btn-ghost" id="in-geojson">Descargar GeoJSON</button><button class="btn btn-sm btn-ghost" id="in-kml">Descargar KML</button></div>
    </div>
    ${tl ? html`<h2 class="section">${dual('Cómo ha ido cambiando', 'Reproducción hora a hora')}</h2>
      <div class="player" role="group" aria-label="Reproducción del incidente">
        <div class="player-time"><strong id="in-time"></strong><span class="tiny muted">${dual('zona con calor:', 'huella:')} <b id="in-area">—</b></span></div>
        <div class="player-controls"><input type="range" id="in-slider" min="0" max="${tl.hours.length - 1}" step="1" value="${tl.hours.length - 1}" aria-label="Hora" /></div>
      </div>
      <div id="in-chart"></div>
      <p class="tiny muted">${dual('La zona marcada en el mapa es todo lo que los satélites vieron caliente: es aproximada y no es el borde oficial del fuego.', tl.footprint_note)}</p>
      ${tl.energia_mj != null || tl.expansion_max_km != null ? html`<p class="tiny muted x-tech">
        ${tl.energia_mj != null ? dual('', `Energía radiativa acumulada: ${fmtNum(tl.energia_mj)} MJ (estimación). `) : ''}
        ${tl.expansion_max_km != null ? dual('', `Mayor expansión: ${fmtNum(tl.expansion_max_km, 1)} km en una hora (estimación). `) : ''}
        ${dual('', `La huella son los píxeles calientes observados: no el frente del fuego ni el perímetro oficial, y con GOES se sobreestima. ${tl.frp_note || ''}`)}</p>` : ''}
      ${S.bands?.features.length ? html`<div class="switch-row"><div class="grow"><b class="small">${dual('El avance por hora en el mapa', 'Bandas por hora + flecha de avance')}</b>
        <div class="tiny muted">${dual('La zona con calor de cada hora, apilada: más intenso = más reciente. La flecha marca hacia dónde se desplazó (estimación).', 'Una banda por frame: la huella acumulada a esa hora; queda arriba la más antigua, así que el color de cada punto dice cuándo llegó el calor ahí. La flecha va del centroide inicial al final y no se dibuja bajo ~2 km (un píxel GOES).')}</div></div>
        <label class="switch"><input type="checkbox" id="in-bands" aria-label="Mostrar el avance por hora en el mapa" ${S.bandsOn ? 'checked' : ''} /><span></span></label></div>` : ''}` : ''}
    <h2 class="section">${dual('Qué vio cada satélite', 'Evidencia')} <span class="tag">${fmtNum(data.evidence_total)}</span></h2>
    <ul class="list evidence-list">${recent.map((e) => html`<li>
      <span class="grow"><span class="event-time">${fmtDateTime(e.observed_at)}</span>
        <span class="small">${dual(`Calor visto por ${sensorWord(e.sensor)} · señal ${confWord(e.confidence)}`,
          `${SENSOR_LABEL[e.sensor] || e.sensor} ${e.satellite || ''} · conf. ${e.confidence || 'n/d'} · FRP ${e.frp_mw != null ? fmtNum(e.frp_mw, 1) : 'n/d'} MW · ${fmtUTC(e.observed_at)} · llegó a BRASA ${e.delay_min} min después`)}</span></span></li>`)}</ul>
    ${data.evidence_total > recent.length ? html`<p class="tiny muted">Se muestran las ${recent.length} más recientes.</p>` : ''}
    ${testigos ? html`<h2 class="section">${dual('Vecinos que ya lo vieron', 'Reportes ciudadanos verificados a ≤ 3 km')}</h2>
      ${testigoRows.length ? html`<ul class="list">${testigoRows.map((r) => html`<li>
        <span class="grow"><span class="event-time">${r.kind_label}</span>
          <span class="small">${dual(`${ago(r.created_at)} · a ${fmtNum(r.distance_km, 1)} km`,
            `${r.kind_label} · ${ago(r.created_at)} (${fmtUTC(r.created_at)}) · ${fmtNum(r.distance_km, 1)} km del centro${r.comuna ? ` · ${r.comuna}` : ''}`)}</span></span></li>`)}</ul>
        ${testigos.reports.length > 5 ? html`<p class="tiny muted">Se muestran los 5 más recientes.</p>` : ''}` : html`
        <p class="small muted">Nadie ha reportado humo o fuego aquí todavía.</p>
        <div class="btn-row"><button class="btn btn-ghost" id="in-testigos-report">Contar lo que veo</button></div>`}` : ''}
    ${latency.length ? html`<div class="callout x-tech" style="margin-top:12px"><b>Latencia (observación → BRASA).</b> ${latency.map(([s, l]) => `${SENSOR_LABEL[s] || s}: mediana ${l.p50_min} min, máx. ${l.max_min} min (${l.n})`).join(' · ')}. Incluye el tiempo de publicación de NASA/NOAA y el ciclo de 10 min de BRASA.</div>` : ''}
    <div class="callout" style="margin-top:12px"><b>${dual('BRASA no es una fuente oficial.', 'Fuente no oficial.')}</b> ${data.official} Emergencias: 132 Bomberos · 130 CONAF.</div>
    <p class="tiny muted x-tech">Incidente ${inc.id} · ${inc.lat.toFixed(4)}, ${inc.lon.toFixed(4)}</p>
    <p class="tiny muted" style="margin-top:10px"><a href="/web/respuesta.html">Tiempos de respuesta oficiales de CONAF</a></p>`);

  container.querySelector('#in-watch').addEventListener('click', () => placeForm(null, { lat: inc.lat, lon: inc.lon, name: inc.comuna ? `Cerca de ${inc.comuna}` : '' }));
  container.querySelector('#in-report').addEventListener('click', () => reportForm({ lat: inc.lat, lon: inc.lon }));
  container.querySelector('#in-share').addEventListener('click', async () => {
    const { title, text } = shareText(inc, info, where);
    // La URL ya va dentro del texto: pasarla también como `url` la duplicaría en Android/Chromium.
    if (navigator.share) {
      try { await navigator.share({ title, text }); return; } catch (err) { if (err?.name === 'AbortError') return; }
    }
    try { await navigator.clipboard.writeText(text); toast('Enlace copiado.'); }
    catch { toast('No se pudo copiar el enlace.', 'error'); }
  });
  container.querySelector('#in-geojson').addEventListener('click', () =>
    download(`brasa-incendio-${inc.id}.geojson`, JSON.stringify(incidentGeoJSON(data)), 'application/geo+json'));
  container.querySelector('#in-kml').addEventListener('click', () =>
    download(`brasa-incendio-${inc.id}.kml`, incidentKML(data), 'application/vnd.google-earth.kml+xml'));
  container.querySelector('#in-testigos-report')?.addEventListener('click', () => reportForm({ lat: inc.lat, lon: inc.lon }));
  container.querySelector('#in-bands')?.addEventListener('change', (e) => { S.bandsOn = e.target.checked; legendAvance(); paintAvance(); });
  S.chart?.destroy();
  S.chart = null;
  legendAvance();
  paintAvance();
  if (!tl) return;
  const host = container.querySelector('#in-chart');
  S.chart = timeChart(host, {
    times: tl.hours.map((h) => h.t), cursor: tl.hours.length - 1, onSeek: (i) => paint(i),
    panels: [
      { id: 'n', title: 'Veces que se vio calor, por hora', kind: 'bars', height: 72,
        series: [{ key: 'goes', label: 'GOES', color: 'var(--series-2)', values: tl.hours.map((h) => h.n_goes) },
          { key: 'polar', label: 'VIIRS/MODIS', color: 'var(--series-1)', values: tl.hours.map((h) => h.n_polar) }] },
      { id: 'cov', title: 'Zona con calor, acumulada', unit: 'ha', kind: 'line', area: true,
        series: [{ key: 'cov', label: 'Huella', color: 'var(--series-2)', values: tl.hours.map((h) => h.footprint_ha || null) }] },
    ],
  });
  container.querySelector('#in-slider').addEventListener('input', (e) => paint(Number(e.target.value)));
  paint(S.index ?? tl.hours.length - 1);
}

async function load(container, id, first) {
  const mine = ++seq;
  /* Los reportes vecinos van en la misma pasada de render: si se pintan después,
   * el contenido queda más bajo justo cuando keepPlace restaura el scroll y el
   * navegador recorta scrollTop (regresión de FIX-05 que pilló el check en CI). */
  const testigosP = api.incidentReports(id).catch(() => null);
  const rayosP = request('/api/opendata/incidents.geojson?hours=336&include_fixed=1&todo=1').catch(() => null);
  let data;
  try { data = await api.incident(id); } catch (err) {
    if (!mounted || mine !== seq) return;
    if (first) {
      container.innerHTML = '<a class="btn btn-sm btn-ghost" href="#/mapa">← Mapa</a><div id="in-err"></div>';
      errorConSalida(container.querySelector('#in-err'), err, () => { if (mounted) load(container, id, true); });
    }
    return;
  }
  const testigos = await testigosP;
  const rayos = await rayosP;
  if (!mounted || mine !== seq) return;
  const keep = S && S.id === id && S.tl && data.timeline && S.index < S.tl.hours.length - 1 ? S.index : null;
  const frames = data.timeline?.frames || [];
  S = { ...(S?.id === id ? S : {}), id, container, evidence: data.evidence, tl: data.timeline, index: keep ?? (data.timeline ? data.timeline.hours.length - 1 : 0),
    bands: bandsGeoJSON(frames), arrow: arrowGeoJSON(frames), bandsOn: (S?.id === id ? S.bandsOn : null) ?? true };
  // OFI-17: el perímetro oficial es estático (estado final): se dibuja una vez, fuera del reproductor.
  const perimeter = data.official_perimeter?.geometry;
  setData('official-perimeter', perimeter ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: perimeter, properties: {} }] } : EMPTY);
  const pbox = perimeter ? geomBbox(perimeter) : null;
  const box = data.timeline ? (pbox ? bboxUnion(data.timeline.bbox, pbox) : data.timeline.bbox) : pbox;
  if (first && box) fitBbox(box, 30);
  keepPlace(container, () => render(container, data, testigos, rayos));
}

export default {
  id: 'incendio',
  nav: false,
  sheet: 'half',
  async mount(container, { rest }) {
    mounted = true;
    clearInterval(timer);
    S?.chart?.destroy();
    S = null;
    show(['detections', 'goes-pixels', 'goes-pixels-line', 'risk-fill', 'explore', 'reports', 'services', 'case-final', 'case-event'], false);
    show(LAYERS, true);
    getMap()?.on('style.load', onStyleLoad);
    $('#map-legend').classList.add('mobile-show');
    const id = rest?.[0] || '';
    container.innerHTML = '<a class="btn btn-sm btn-ghost" href="#/mapa">← Mapa</a><h1 class="view-title" style="margin-top:12px">Cargando el incidente…</h1>';
    await load(container, id, true);
    timer = setInterval(() => { if (document.visibilityState === 'visible') load(container, id, false); }, REFRESH_MS);
  },
  unmount() {
    mounted = false;
    seq++;
    clearInterval(timer);
    S?.chart?.destroy();
    S = null;
    for (const id of ['case-goes', 'case-points', 'case-footprint', 'official-perimeter']) setData(id, EMPTY);
    show(LAYERS, false);
    const map = getMap();
    map?.off('style.load', onStyleLoad);
    if (map) {
      for (const id of BAND_LAYERS) if (map.getLayer(id)) map.removeLayer(id);
      for (const id of [BAND_SOURCE, ARROW_SOURCE]) if (map.getSource(id)) map.removeSource(id);
    }
    $('#map-legend').innerHTML = '';
    $('#map-legend').classList.remove('mobile-show');
  },
};
