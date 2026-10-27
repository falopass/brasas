/* Mapa en vivo: focos de calor GOES + VIIRS/MODIS, capas, fuentes y exploración histórica FIRMS. */
import { api, request } from '../api.js';
import { buscarLugares } from '../buscador.js';
import { CAPAS, capasFromUrl, capasToUrl, senapredPorComuna, toggleCapa } from '../capas.js';
import { AGE_BINS, basemap, BASEMAPS, EMPTY_FC, fitBbox, fly, getMap, LIGHTNING_COLOR, pointsGeoJSON, RAIN_COLORS, registrarToque, RISK_COLORS, SENAPRED_COLORS, setBasemap, setData, setRain, setRelieve, setRisk, setSenapred, show, SMOKE_COLOR } from '../map.js';
import { isReliable, loadObservations, visibleObservations } from '../data.js';
import { errorConSalida } from '../errores.js';
import { store } from '../store.js';
import { incidentInfo } from './incendio.js';
import { abrirPopup, cerrarPopup, OFFICIAL_LABEL, OFFICIAL_TONE, popupFoco, popupIncidente, popupOficial } from '../popup.js';
import { testigos } from '../reportes.js';
import { openModal, reportForm } from '../ui.js';
import { $, ago, bearingDeg, cardinal, dual, fmtDateTime, fmtNum, haversineKm, html, keepPlace, minutesSince, RISK, SENSOR_LABEL, toast, todayChile } from '../util.js';

const RANGES = [[6, 'Últimas 6 horas', '6 h'], [24, 'Hoy', '24 h'], [48, '2 días', '48 h'], [168, 'Semana', '7 días']];
const SOURCE_NAMES = {
  GOES19_FDCF: 'GOES-19 · cada 10 min', GOES16_FDCF: 'GOES-16', VIIRS_NOAA20_NRT: 'VIIRS NOAA-20', VIIRS_NOAA21_NRT: 'VIIRS NOAA-21',
  VIIRS_SNPP_NRT: 'VIIRS Suomi NPP', MODIS_NRT: 'MODIS Terra/Aqua',
};
let mounted = false;
// Soltar() de cada registrarToque (MAPA-157): se invocan todas al desmontar.
let soltar = [];
let layersEl = null;
let smokeMeta = null;
// Alertas SENAPRED de la capa nacional (OFI-207): {code: [alertas]} y su marca de descarga.
let senapredPorCode = {};
let senapredFetchedAt = null;
// Primera carga diferida: la casilla sigue enfocable mientras llega (MAPA-141).
const cargando = new Set();
const layers = { focos: true, incendios: true, risk: false, rain: false, reports: true, places: true, hulls: false, lightning: false, aire: false, scars: false, senapred: false, relieve: false };
// MAPA-164: las casillas se ordenan por tema (fuego / contexto / tú); estado y URL siguen en CAPAS.
const GRUPOS_CAPAS = [
  ['Fuego', ['focos', 'incendios', 'hulls', 'lightning']],
  ['Contexto', ['risk', 'rain', 'senapred', 'aire', 'scars', 'viento', 'relieve']],
  ['Tú', ['places', 'reports']],
];
// Los cinco niveles de anomalía de lluvia que calcula backend/rain.py (leyenda corta).
const RAIN_LEVELS = [['muy_seco', 'Mucho menos'], ['seco', 'Menos'], ['normal', 'Normal'], ['humedo', 'Más'], ['muy_humedo', 'Mucho más']];
// Clases de alerta SENAPRED (OFI-207): etiqueta corta de leyenda y tono de la insignia.
const SENAPRED_TIPOS = [['roja', 'Roja'], ['amarilla', 'Amarilla'], ['temprana_preventiva', 'Temprana preventiva'], ['otra', 'Otra alerta']];
const SENAPRED_TITULO = { roja: 'Alerta roja', amarilla: 'Alerta amarilla', temprana_preventiva: 'Alerta temprana preventiva', otra: 'Alerta oficial' };
const SENAPRED_TONO = { roja: 'urgente', amarilla: 'aviso', temprana_preventiva: 'tranquilo', otra: '' };

/** Fuente y hora de cada capa encendida (MAPA-01), en una línea discreta bajo los colores. */
function layerSources() {
  const parts = [];
  const status = store.get('status');
  if (layers.focos) parts.push(`focos: GOES-19, VIIRS y MODIS${status?.last_ingest_at ? `, ${ago(status.last_ingest_at)}` : ''}`);
  if (layers.incendios) {
    const run = (status?.runs || []).find((r) => (r.product || '').includes('CONAF'));
    parts.push(`incendios: CONAF${run?.finished_at ? `, ${ago(run.finished_at)}` : ''}`);
  }
  const risk = store.get('risk');
  if (layers.risk && risk) parts.push(`peligro: Open-Meteo, cálculo BRASA${risk.computed_at ? `, ${ago(risk.computed_at)}` : ''}`);
  if (layers.aire && smokeMeta?.generated_at) parts.push(`humo: NOAA GOES-19, ${ago(smokeMeta.generated_at)}`);
  if (layers.senapred) parts.push(`alertas: SENAPRED${senapredFetchedAt ? `, ${ago(senapredFetchedAt)}` : ''}`);
  return parts.length ? html`<div class="legend-note">${parts.join(' · ')}</div>` : '';
}

function legend() {
  const leg = $('#map-legend');
  leg.innerHTML = String(html`${layers.focos ? html`<button type="button" class="legend-title legend-fold" aria-expanded="${leg.classList.contains('legend-closed') ? 'false' : 'true'}">¿Hace cuánto se vio el calor?</button>
    <div class="legend-row">${AGE_BINS.map((b) => html`<span class="legend-item"><span class="sw" style="background:${b.color}"></span>${b.label}</span>`)}</div>` : ''}
    ${layers.focos || layers.incendios || layers.reports ? html`<div class="legend-row" style="margin-top:4px">
      ${layers.focos ? html`<span class="legend-item"><span class="sw sw-sq" style="background:#ff7a2e;opacity:.6"></span>${dual('Zona de unos 2 km', 'Píxel GOES (~2–3 km)')}</span>
      <span class="legend-item"><span class="sw" style="background:#ff7a2e"></span>${dual('Punto más preciso', 'VIIRS/MODIS')}</span>` : ''}
      ${layers.incendios ? html`<span class="legend-item"><span class="sw sw-ring"></span>${dual('Incendio que informa CONAF', 'Incendio CONAF (oficial)')}</span>` : ''}
      ${layers.reports ? html`<span class="legend-item"><span class="sw" style="background:#6250d6"></span>Aviso de vecino revisado</span>` : ''}</div>` : ''}
    ${layers.focos ? html`<div class="legend-note">${dual('El tamaño sube con la potencia del calor. De lejos los focos se agrupan: el número cuenta focos de calor, no incendios. El anillo de colores es un posible incendio: tócalo para ver su ficha. De cerca, su contorno y su nombre marcan la zona aproximada donde se vio calor: no es el perímetro oficial.', 'Radio por FRP; bajo zoom 7 decimación por celda con conteo, más un anillo por incidente abierto (color = estado). Desde zoom 7 el contorno de la huella y desde zoom 8 su etiqueta — zona aproximada, no perímetro oficial — que abren la ficha del incidente.')}</div>` : ''}
    ${layers.risk ? html`<div class="legend-row" style="margin-top:4px">${Object.entries(RISK).map(([k, r]) => html`<span class="legend-item"><span class="sw" style="background:${RISK_COLORS[k]}"></span>${r.label}</span>`)}</div>
      <div class="legend-note">${dual('Cada nivel tiene además su trama.', 'Cada nivel se distingue también por su trama, no solo por el color.')}</div>` : ''}
    ${layers.rain ? html`<div class="legend-row" style="margin-top:4px">${RAIN_LEVELS.map(([k, label]) => html`<span class="legend-item"><span class="sw" style="background:${RAIN_COLORS[k]}"></span>${label}</span>`)}</div>
      <div class="legend-note">Junio–hoy vs. normal 1991-2020. Es contexto del combustible, no cambia el peligro de hoy.${store.get('risk')?.rain_source?.name ? ` Fuente: ${store.get('risk').rain_source.name}.` : ''}</div>` : ''}
    ${layers.senapred ? html`<div class="legend-row" style="margin-top:4px">${SENAPRED_TIPOS.map(([k, label]) => html`<span class="legend-item"><span class="sw" style="background:${SENAPRED_COLORS[k]}"></span>${label}</span>`)}</div>
      <div class="legend-note">Texto oficial de SENAPRED. BRASA no emite alertas.</div>` : ''}
    ${layers.relieve ? html`<div class="legend-note" style="margin-top:4px">Relieve: sombreado Mapterhorn · Copernicus DEM GLO-30.</div>` : ''}
    ${layers.hulls ? html`<div class="legend-note" style="margin-top:4px">Huella aproximada de BRASA: no es el perímetro oficial.</div>` : ''}
    ${layers.lightning ? html`<div class="legend-row" style="margin-top:4px"><span class="legend-item"><span class="sw" style="background:${LIGHTNING_COLOR}"></span>Rayo visto por el satélite (última hora)</span></div>
      <div class="legend-note">Un rayo no es un incendio: sobre pasto seco puede ser el inicio de uno.</div>` : ''}
    ${layers.scars ? html`<div class="legend-row" style="margin-top:4px"><span class="legend-item"><span class="sw sw-sq" style="background:#8a4b2a;opacity:.5"></span>${dual('Zona con calor esta temporada', 'Cicatriz: huella de detecciones, no perímetro')}</span></div>` : ''}
    ${layers.viento ? html`<div class="legend-row" style="margin-top:4px"><span class="legend-item"><span class="sw" style="background:#5aa0d8"></span>Partículas: viento estimado a 10 m · Open-Meteo${vientoEdadTxt ? ` · ${vientoEdadTxt}` : ''}</span></div>` : ''}
    ${layers.aire ? html`<div class="legend-row" style="margin-top:4px"><span class="legend-item"><span class="sw sw-sq" style="background:${SMOKE_COLOR[store.get('theme')]}"></span>Humo visto por el satélite</span></div>
      <div class="legend-note">${dual('Es humo en el aire, no fuego confirmado.', 'Máscara de aerosol ABI-L2-ADPF: aerosol, no detección térmica.')}</div>` : ''}
    ${layerSources()}
    ${layers.focos ? html`<div class="legend-note esencial">${dual('Calor no siempre es incendio. Los puntos pálidos son dudosos.', 'Un foco de calor no confirma un incendio. Los puntos tenues tienen confianza baja.')}</div>` : ''}`);
}

/** Incidentes con evidencia de fuego (no anomalías sueltas ni fuentes fijas), desde las observaciones ya cargadas. */
function fireIncidents(points) {
  const by = new Map();
  for (const o of points) {
    if (!o.incident_id || o.incident_fixed || !['posible', 'reportado', 'confirmado', 'controlado'].includes(o.incident_status)) continue;
    const inc = by.get(o.incident_id) || { id: o.incident_id, status: o.incident_status, n: o.incident_n, last: o.observed_at, comuna: o.comuna, region: o.region };
    if (o.observed_at > inc.last) inc.last = o.observed_at;
    by.set(o.incident_id, inc);
  }
  return [...by.values()].sort((a, b) => (a.last < b.last ? 1 : -1));
}

// UX-78: los mismos nombres que declara el backend (backend/providers/overpass.py).
const SERVICE_LABEL = { assembly_point: 'Punto de encuentro', hospital: 'Hospital', clinic: 'Centro de salud', fire_station: 'Cuartel de Bomberos', police: 'Carabineros' };

async function loadOfficial() {
  try {
    const data = await api.officialFires();
    if (!mounted) return;
    store.set('official', data);
    // «label» alimenta la etiqueta del mapa desde zoom 8 (MAPA-163): «CONAF: «Nombre» · En curso».
    setData('official', pointsGeoJSON(data.fires, (f) => ({ id: f.id, status: f.status,
      label: `CONAF: «${f.name || 'Sin nombre'}» · ${f.status_raw || OFFICIAL_LABEL[f.status]}` })));
  } catch { /* sin conexión: se mantiene lo último */ }
}

/** Ancla de la ficha: en un punto, su coordenada; en un polígono, donde cayó el toque. */
const puntoDe = (feature, lngLat) => (feature?.geometry?.type === 'Point' ? feature.geometry.coordinates : lngLat);

function bindMap() {
  const map = getMap();
  const onDetection = (feature, lngLat) => {
    const props = feature?.properties;
    // Una celda agrupa varios focos (MAPA-01): tocarla acerca hasta separarlos, no abre ficha.
    if (props?.count > 1) {
      map.easeTo({ center: lngLat, zoom: Math.min(map.getZoom() + 1.8, 10.5), duration: 600 });
      return;
    }
    const obs = (store.get('observations') || []).find((o) => o.id === props?.id);
    if (obs) popupFoco(obs, puntoDe(feature, lngLat));
  };
  const onReport = (feature, lngLat) => {
    const p = feature.properties;
    abrirPopup(puntoDe(feature, lngLat), html`<div class="tiny">Aviso de un vecino, revisado por BRASA</div>
      <b>${p.kind_label}</b> · <span class="muted">${ago(p.created_at)}</span><p class="small" style="margin-top:6px">${p.description || 'Sin descripción.'}</p>
      ${p.has_photo ? html`<img class="photo" alt="Foto del reporte" src="/api/reports/${p.id}/photo" />` : ''}
      ${testigos(p) ? html`<div class="tiny">${testigos(p)}</div>` : ''}
      <div class="tiny muted">Lo revisó un voluntario de BRASA. No es información oficial.</div>`);
  };
  const onRisk = (feature, lngLat) => {
    if (!layers.risk) return;
    const props = feature.properties;
    const r = store.get('risk')?.comunas?.[props.code];
    abrirPopup(lngLat, html`<b>${props.name}</b><div class="tiny muted">${props.region}</div>
      <div style="margin-top:6px">${r ? html`<span class="risk-chip ${RISK[r.level].cls}">Peligro ${RISK[r.level].label.toLowerCase()}</span>
      <p class="small" style="margin:6px 0 0">${RISK[r.level].plain}</p>
      <div class="small muted" style="margin-top:4px">Hasta ${fmtNum(r.tmax)} °C · humedad ${fmtNum(r.rhmin)} % · viento ${fmtNum(r.windmax)} km/h</div>` : 'Aún sin pronóstico.'}</div>
      <a class="btn btn-sm" style="margin-top:8px" href="#/riesgo?comuna=${props.code}">Ver los próximos días</a>`, '260px');
  };
  const onRain = (feature, lngLat) => {
    if (!layers.rain) return;
    const props = feature.properties;
    const r = store.get('risk')?.rain?.[props.code];
    abrirPopup(lngLat, html`<b>${props.name}</b><div class="tiny muted">${props.region}</div>
      <div style="margin-top:6px">${r ? html`<b class="small">${r.label}</b>
      <p class="small" style="margin:6px 0 0">${r.plain}</p>
      <div class="small muted" style="margin-top:4px">${fmtNum(r.current_mm)} mm desde junio · lo normal son ${fmtNum(r.normal_mm)} mm</div>` : 'Aún sin dato de lluvia para esta comuna.'}</div>`, '260px');
  };
  const onSenapred = (feature, lngLat) => {
    if (!layers.senapred) return;
    const props = feature.properties;
    const alertas = senapredPorCode[props.code] || [];
    abrirPopup(lngLat, html`<b>${props.name}</b><div class="tiny muted">${props.region}</div>
      ${alertas.map((a) => html`<div style="margin-top:8px"><span class="status-badge${SENAPRED_TONO[a.tipo] ? ` st-${SENAPRED_TONO[a.tipo]}` : ''}">${SENAPRED_TITULO[a.tipo] || 'Alerta oficial'}</span>
        <p class="small" style="margin:4px 0 0">${a.title}</p>
        <div class="tiny muted" style="margin-top:4px">${a.issued_at ? fmtDateTime(a.issued_at) : ''} · <a href="${a.url}" target="_blank" rel="noopener">Ver en SENAPRED</a></div></div>`)}
      ${alertas.length ? '' : html`<p class="small" style="margin-top:6px">Ninguna alerta vigente nombra esta comuna.</p>`}
      <div class="tiny muted" style="margin-top:8px">Texto oficial de SENAPRED. BRASA no emite alertas.</div>`);
  };
  const onIncidente = (feature, lngLat) => {
    const inc = incidentesPorId.get(feature?.properties?.id);
    if (inc) popupIncidente(inc, puntoDe(feature, lngLat));
  };
  const onOfficial = (feature, lngLat) => {
    const id = feature?.properties?.id;
    const fire = store.get('official')?.fires?.find((f) => f.id === id);
    if (fire) popupOficial(fire, puntoDe(feature, lngLat));
  };
  const onLightning = (feature, lngLat) => {
    if (!layers.lightning) return;
    const p = feature.properties;
    abrirPopup(puntoDe(feature, lngLat), html`
      <div class="tiny">Rayo visto por el satélite GOES-19</div>
      <b>${ago(p.observed_at)}</b> · <span class="muted">${fmtDateTime(p.observed_at)}</span>
      ${p.energy_j ? html`<div class="small" style="margin-top:4px">Energía ${fmtNum(p.energy_j)} J${p.area_km2 ? ` · área ~${fmtNum(p.area_km2)} km²` : ''}</div>` : ''}
      <div class="tiny muted" style="margin-top:6px">Un rayo no es un incendio: es luz de tormenta vista desde el espacio.</div>`, '260px');
  };
  const onScars = (feature, lngLat) => {
    if (!layers.scars) return;
    const p = feature.properties;
    abrirPopup(lngLat, html`<b>${p.comuna}</b><div class="tiny muted">${p.region}</div>
      <div class="small" style="margin-top:6px">${dual(`El satélite vio calor aquí esta temporada: unas ${fmtNum(p.ha)} ha en ${p.n_incidentes} ${p.n_incidentes === 1 ? 'incidente' : 'incidentes'}.`, `Huella de detecciones: ${fmtNum(p.ha)} ha · ${p.n_incidentes} ${p.n_incidentes === 1 ? 'incidente' : 'incidentes'} · ${p.desde?.slice(0, 10)} a ${p.hasta?.slice(0, 10)}.`)}</div>
      <div class="tiny muted" style="margin-top:6px">${dual('No es el perímetro oficial del incendio: es la zona donde se observó calor.', 'Fuente: huella BRASA de detecciones satelitales, no CONAF.')}</div>`, '260px');
  };
  const onService = (feature, lngLat) => {
    const p = feature.properties;
    const [lon, lat] = feature.geometry.coordinates;
    abrirPopup(puntoDe(feature, lngLat), html`<b>${p.name}</b>
      <div class="tiny muted">${SERVICE_LABEL[p.kind] || p.kind_label || 'Servicio'}</div>
      <p class="small" style="margin-top:6px"><a href="https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}">Cómo llegar</a>. Sigue las rutas y los puntos que indique la autoridad: los puntos de OpenStreetMap pueden no ser los oficiales.</p>`, '260px');
  };
  soltar = [['detections', onDetection], ['goes-pixels', onDetection], ['reports', onReport], ['risk-fill', onRisk], ['rain-fill', onRain], ['senapred-fill', onSenapred], ['official', onOfficial], ['official-labels', onOfficial], ['incident-rings', onIncidente], ['incident-labels', onIncidente], ['incident-hulls-line', onIncidente], ['lightning', onLightning], ['scars-fill', onScars], ['services', onService]]
    .map(([capa, fn]) => registrarToque(capa, fn));
}

async function loadRisk() {
  try {
    const risk = await api.risk(todayChile());
    store.set('risk', risk);
    setRisk(risk.comunas);
    setRain(risk.rain);
    if (mounted) legend();
    if (!Object.keys(risk.comunas).length) toast('El pronóstico de peligro aún no está listo. Vuelve en unos minutos.', 'info');
  } catch (err) { toast(err.message, 'error'); }
}

async function loadReports() {
  try {
    const { reports } = await api.reports();
    setData('reports', pointsGeoJSON(reports));
  } catch { /* sin reportes */ }
}

/** /api/incidents alimenta anillos país (MAPA-152), contorno z≥7 y etiquetas z≥8 (MAPA-163);
 *  «Huellas» suma el relleno (DET-10). Anomalías: sin anillo (no son incendios). */
const RING_STATUS = new Set(['posible', 'reportado', 'confirmado', 'controlado']);
// El incidente detrás de cada feature del mapa, para su ficha (MAPA-163).
let incidentesPorId = new Map();
async function loadIncidents() {
  try {
    const data = await api.incidents(store.get('obsHours'), true);
    if (!mounted) return;
    incidentesPorId = new Map(data.incidents.map((i) => [i.id, i]));
    setData('incident-hulls', {
      type: 'FeatureCollection',
      features: data.incidents.filter((i) => i.hull)
        .map((i) => ({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [i.hull] }, properties: { id: i.id, status: i.status } })),
    });
    setData('incident-rings', pointsGeoJSON(
      data.incidents.filter((i) => RING_STATUS.has(i.status)),
      (i) => ({ id: i.id, status: i.status, n: i.n_obs, label: `${incidentInfo(i).short}${i.comuna ? ` · ${i.comuna}` : ''}` })));
  } catch (err) { toast(err.message, 'error'); }
}

/* MAPA-163: cada lote nuevo de focos repide incidentes y CONAF — máx. 1/min y solo con la
 * pestaña visible (los focos ya se actualizan solos cada 2 min; el resto los acompaña). */
const REFRESCO_INCIDENTES_MS = 60_000;
let ultimoRefrescoIncidentes = 0;
function alLlegarObservaciones() {
  if (!mounted || document.visibilityState !== 'visible') return;
  const ahora = Date.now();
  if (ahora - ultimoRefrescoIncidentes < REFRESCO_INCIDENTES_MS) return;
  ultimoRefrescoIncidentes = ahora;
  loadIncidents();
  loadOfficial();
}

/* Enlaces profundos de «Compartir» (MAPA-165): foco=<id> y conaf=<id> se resuelven al
 * llegar su dato (observaciones al montar o en el primer sondeo; CONAF con loadOfficial).
 * Si el punto ya salió de la ventana, aviso y el mapa queda en la ubicación del enlace. */
const AVISO_PUNTO_PERDIDO = 'Ese punto ya no está entre los focos de las últimas horas; el mapa queda en su ubicación.';
let pendienteFoco = null;
let pendienteConaf = null;
function intentarEnlace() {
  if (!mounted) return;
  if (pendienteFoco && store.get('dataAsOf')) {
    const id = pendienteFoco;
    pendienteFoco = null;
    const obs = (store.get('observations') || []).find((o) => String(o.id) === String(id));
    if (obs) popupFoco(obs, [obs.lon, obs.lat]);
    else toast(AVISO_PUNTO_PERDIDO, 'info');
  }
  if (pendienteConaf && store.get('official')) {
    const id = pendienteConaf;
    pendienteConaf = null;
    const fire = (store.get('official').fires || []).find((f) => String(f.id) === String(id));
    if (fire) popupOficial(fire, [fire.lon, fire.lat]);
    else toast(AVISO_PUNTO_PERDIDO, 'info');
  }
}

/** Destellos GLM de la última hora al encender el switch; si falla, el switch vuelve a apagado. */
async function loadLightning(input) {
  try {
    const res = await fetch('/api/opendata/lightning.geojson?hours=1');
    const body = await res.json().catch(() => null);
    if (!res.ok || !body?.features) {
      throw new Error(typeof body?.detail === 'string' ? body.detail : `Los rayos no están disponibles ahora (error ${res.status}).`);
    }
    setData('lightning', body);
  } catch (err) {
    layers.lightning = false;
    if (input) input.checked = false;
    setData('lightning', EMPTY_FC);
    applyLayers();
    toast(err instanceof TypeError ? 'Sin conexión con el servidor: no se pudieron cargar los rayos.' : err.message, 'error');
  }
}

/** Alertas SENAPRED vigentes (OFI-207): pinta las comunas de cada título con su clase más
 *  grave. Si falla, el switch vuelve a apagado; la fuente ya degrada a `[]` por su cuenta. */
async function loadSenapred(input) {
  try {
    const data = await request('/api/senapred/alertas');
    if (!mounted) return;
    const { tipos, porComuna } = senapredPorComuna(data?.alerts);
    senapredPorCode = porComuna;
    senapredFetchedAt = data?.fetched_at || null;
    setSenapred(tipos);
    legend();
  } catch (err) {
    layers.senapred = false;
    if (input) input.checked = false;
    senapredPorCode = {};
    applyLayers();
    toast(err instanceof TypeError ? 'Sin conexión con el servidor: no se pudieron cargar las alertas.' : err.message, 'error');
    syncCapaInputs();
    legend();
  }
}

/** Cicatrices de la temporada (AGUA-01): huella de detecciones por comuna, solo al encender la capa. */
async function loadScars() {
  try {
    setData('scars', await api.scars());
  } catch { /* sin cicatrices: la capa queda vacía */ }
}

/** Humo GOES-19 (capa «aire», DET-16): aerosol de la última hora; si falla, el switch se apaga. */
let vientoEdadTxt = '';
async function loadWind(input) {
  // Sin grilla aún (404) o atrasada, la casilla se revierte o se avisa: no puede quedar
  // encendida sobre una capa vacía.
  try {
    const mod = await import('../viento.js');
    const estado = await mod.encender(input);
    const min = mod.edadGrillaMin();
    vientoEdadTxt = min === null ? '' : (min < 1 ? 'recién calculada' : `datos de hace ${Math.round(min / 60)} h`);
    if (estado === 'vieja') toast(`La grilla de viento tiene más de 12 horas: no se anima (${vientoEdadTxt}).`, 'error');
    legend();
  } catch {
    layers.viento = false;
    if (input) input.checked = false;
    vientoEdadTxt = '';
    applyLayers();
    toast('La grilla de viento todavía no está lista: el ciclo la calcula cada 6 horas.', 'error');
    legend();
  }
}

async function loadSmoke(input) {
  try {
    const { loadSmoke: fetchSmoke } = await import('../smoke.js');
    const body = await fetchSmoke();
    smokeMeta = { generated_at: body.generated_at };
    setData('smoke', body);
  } catch (err) {
    layers.aire = false;
    if (input) input.checked = false;
    setData('smoke', EMPTY_FC);
    applyLayers();
    toast(err instanceof TypeError ? 'Sin conexión con el servidor: no se pudo cargar el humo.'
      : (err?.message || 'El humo de GOES no está disponible ahora.'), 'error');
  }
}

// ------------------------------------------------------------------ capas conmutables (MAPA-01)
// El control flotante (#map-layers) y los switches del panel usan el mismo `layers` y el
// mismo setCapa; el estado de las capas del control se refleja en #/mapa?capas=….
function updateCapasUrl() {
  if (!mounted || !location.hash.startsWith('#/mapa')) return;
  const [path, query = ''] = location.hash.replace(/^#\/?/, '').split('?');
  const params = new URLSearchParams(query);
  params.set('capas', capasToUrl(layers));
  history.replaceState(null, '', `#/${path}?${params}`);
}

function syncCapaInputs() {
  layersEl?.querySelectorAll('[data-capa]').forEach((i) => { i.checked = Boolean(layers[i.dataset.capa]); });
  const count = layersEl?.querySelector('.layers-count');
  if (count) count.textContent = `${CAPAS.filter((c) => layers[c.key]).length} de ${CAPAS.length}`;
  const offline = layersEl?.querySelector('#capas-offline');
  if (offline) offline.hidden = !store.get('basemapOffline');
}

function announceCapa(key) {
  const live = layersEl?.querySelector('#capas-live');
  const capa = CAPAS.find((c) => c.key === key);
  if (live && capa) live.textContent = `«${capa.label}» ${layers[key] ? 'activada' : 'desactivada'}`;
}

/** Prende o apaga una capa desde el control o desde el panel; carga lo que haga falta. */
async function setCapa(key, checked, input) {
  Object.assign(layers, toggleCapa(layers, key, checked));
  // La casilla no se deshabilita mientras carga: un input deshabilitado suelta el foco y el
  // siguiente Tab se salta la capa (MAPA-141). La carga doble se evita con `cargando`.
  const lazy = { aire: loadSmoke, lightning: loadLightning, viento: loadWind, senapred: loadSenapred }[key];
  if (key === 'aire' && !checked) setData('smoke', EMPTY_FC);
  if (key === 'viento' && !checked) { vientoEdadTxt = ''; import('../viento.js').then((m) => m.apagar()); legend(); }
  if (key === 'lightning' && !checked) setData('lightning', EMPTY_FC);
  // Resumen y leyenda responden al instante: la capa queda prendida aunque su dato demore
  // en llegar; si la carga falla, el propio loader la revierte y applyLayers la suelta.
  applyLayers();
  if (checked && lazy && !cargando.has(key)) {
    cargando.add(key);
    try { await lazy(input); } finally { cargando.delete(key); }
    applyLayers();
  }
  if (['risk', 'rain'].includes(key) && checked) await loadRisk();
  if (key === 'hulls' && checked) await loadIncidents();
  if (key === 'scars' && checked) await loadScars();
  syncCapaInputs();
  if (CAPAS.some((c) => c.key === key)) updateCapasUrl();
  legend();
  announceCapa(key);
}

// Índice liviano de comunas para el buscador (MAPA-21): se usa el que ya cargó app.js
// y, si aún no está, se pide una vez al abrir el buscador (misma URL, sin endpoint nuevo).
let comunasPromise = null;
function loadComunasIndex() {
  const cached = store.get('comunasIndex');
  if (cached?.length) return Promise.resolve(cached);
  comunasPromise ??= fetch('/web/data/comunas-index.json')
    .then((res) => res.json())
    .then((index) => {
      const ordenado = index.sort((a, b) => a.name.localeCompare(b.name, 'es'));
      store.set('comunasIndex', ordenado);
      return ordenado;
    })
    .catch(() => { comunasPromise = null; return []; });
  return comunasPromise;
}

// Localidades (MAPA-167): índice diferido, se pide al usar el buscador.
let localidadesPromise = null;
function loadLocalidades() {
  localidadesPromise ??= fetch('/web/data/localidades.json')
    .then((res) => res.json())
    .then((filas) => filas.map(([name, comuna, tipo, lat, lon]) => ({ name, comuna, tipo, lat, lon })))
    .catch(() => { localidadesPromise = null; return []; });
  return localidadesPromise;
}

/** Zoom que deja la comuna entera a la vista; `fly` suma además los márgenes del mapa. */
function zoomParaBbox([w, s, e, n]) {
  const map = getMap();
  const ancho = map?.getContainer()?.clientWidth || 1024;
  const alto = map?.getContainer()?.clientHeight || 640;
  const rad = Math.PI / 180;
  const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * rad) / 2));
  const fx = Math.abs(e - w) / 360;
  const fy = Math.abs(mercY(n) - mercY(s)) / (2 * Math.PI);
  if (!fx && !fy) return 10;
  const zx = fx ? Math.log2((0.7 * ancho) / (512 * fx)) : Infinity;
  const zy = fy ? Math.log2((0.7 * alto) / (512 * fy)) : Infinity;
  return Math.max(8, Math.min(12, Math.floor(Math.min(zx, zy))));
}

/** Buscador de comunas y localidades (MAPA-21/MAPA-164/MAPA-167) enchufado a
 *  `#map-search`/`#map-search-results`: al elegir vuela al lugar y corre `onElegir`. */
function bindBuscarComuna(root, onElegir) {
  const search = root.querySelector('#map-search');
  const results = root.querySelector('#map-search-results');
  if (!search || !results) return;
  let hits = [];
  let turno = 0;
  const enfocar = () => {
    // En celular el teclado se come la hoja en «peek»: al enfocar el campo la hoja
    // sube a «full» y el campo queda a la vista con los resultados debajo.
    if (matchMedia('(max-width: 899px)').matches) {
      document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'full' }));
      search.scrollIntoView({ block: 'nearest' });
    }
    pintar();
  };
  const pintar = async () => {
    const mio = ++turno;
    const [index, localidades] = await Promise.all([loadComunasIndex(), loadLocalidades()]);
    if (mio !== turno) return;
    hits = buscarLugares(index, localidades, search.value);
    results.innerHTML = hits.length
      ? String(html`${hits.map((h, i) => html`<button type="button" class="search-hit" data-h="${i}"><span>${h.name}</span><span class="tiny">${h.kind === 'localidad' ? `${h.tipo}${h.comuna ? ` · ${h.comuna}` : ''}` : h.region}</span></button>`)}`)
      : search.value.trim() ? '<p class="tiny muted">No encontramos ese lugar.</p>' : '';
  };
  const elegir = (i) => {
    const hit = hits[i];
    if (!hit) return;
    search.value = '';
    results.innerHTML = '';
    onElegir?.(); // primero la hoja: su setPadding cancelaría el flyTo
    if (hit.kind === 'localidad') {
      fly(hit.lon, hit.lat, 12.5); // la localidad es un punto, no tiene polígono
    } else {
      const [lon, lat] = hit.center;
      fly(lon, lat, hit.bbox ? zoomParaBbox(hit.bbox) : 10);
    }
  };
  search.addEventListener('focus', enfocar);
  search.addEventListener('input', pintar);
  search.addEventListener('search', pintar);
  results.addEventListener('click', (e) => {
    const boton = e.target.closest('[data-h]');
    if (boton) elegir(Number(boton.dataset.h));
  });
}

// El título de la leyenda la repliega a una píldora; la clase queda en el
// contenedor persistente y sobrevive a los repintes de legend().
$('#map-legend')?.addEventListener('click', (e) => {
  const b = e.target.closest('.legend-fold');
  if (b) b.setAttribute('aria-expanded', String(!$('#map-legend').classList.toggle('legend-closed')));
});

/** Control compacto sobre el mapa: un `<details>` con el fondo arriba y las capas
 *  conmutables agrupadas (Fuego / Contexto / Tú, MAPA-164). Los checkboxes son
 *  operables con teclado; el estado se anuncia vía #capas-live. */
function mountLayersControl() {
  if (layersEl) return;
  const wrap = $('.map-wrap');
  if (!wrap) return;
  layersEl = document.createElement('details');
  layersEl.className = 'map-layers';
  layersEl.id = 'map-layers';
  layersEl.addEventListener('toggle', () => {
    // Una cosa abierta a la vez: si «Capas» se abre, leyenda y filtros se repliegan.
    if (!layersEl.open) return;
    $('#map-legend')?.classList.remove('legend-open');
    $('#legend-chip')?.setAttribute('aria-expanded', 'false');
    const f = $('#map-filters'); if (f) f.open = false;
  });
  // El anuncio va dentro del <summary>: el resto del <details> cerrado no se renderiza.
  layersEl.innerHTML = String(html`<summary><span>Capas</span><span class="layers-count" aria-hidden="true"></span><span class="sr-only" id="capas-live" role="status"></span></summary>
    <div class="layers-body">
      <div class="layers-group" role="group" aria-label="Fondo del mapa">
        <div class="layers-group-title">Fondo</div>
        <div class="segmented" role="group" aria-label="Fondo del mapa">${Object.entries(BASEMAPS).map(([k, b]) => html`<button type="button" data-basemap="${k}" aria-pressed="${basemap() === k}">${b.label}</button>`)}</div>
        <p class="tiny" id="capas-offline" hidden>El fondo del mapa no carga ahora; se muestran solo los límites de las comunas.</p>
      </div>
      ${GRUPOS_CAPAS.map(([titulo, keys]) => html`<div class="layers-group" role="group" aria-label="Capas: ${titulo}">
        <div class="layers-group-title">${titulo}</div>
        ${keys.map((key) => { const c = CAPAS.find((x) => x.key === key); return html`
          <div class="switch-row"><div class="grow"><b class="small">${c.label}</b></div>
            <label class="switch"><input type="checkbox" data-capa="${c.key}" aria-label="${c.aria}" /><span></span></label></div>`; })}
      </div>`)}
    </div>`);
  // La fila .map-ctl junta chips + Capas + Leyenda en celular; en escritorio es
  // display:contents y «Capas» sigue siendo la tarjeta flotante de siempre.
  const dock = $('#map-ctl') || wrap;
  dock.insertBefore(layersEl, dock.querySelector('#legend-chip'));
  layersEl.querySelectorAll('[data-capa]').forEach((input) => input.addEventListener('change', () => setCapa(input.dataset.capa, input.checked, input)));
  layersEl.querySelectorAll('[data-basemap]').forEach((b) => b.addEventListener('click', () => {
    setBasemap(b.dataset.basemap);
    layersEl.querySelectorAll('[data-basemap]').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.basemap === basemap())));
  }));
}

/** Filtros sobre el mapa (MAPA-164), solo en pantalla angosta: los mismos filtros
 *  del panel agrupados en la píldora desplegable «Filtros» — igual a «Capas» y
 *  «Leyenda», la fila son tres controles uniformes; se reflejan con `syncMapChips`
 *  en cada cambio del store. */
let chipsEl = null;
let filtrosEl = null;
async function setHoras(hours) {
  store.set('obsHours', hours);
  try { const data = await loadObservations(); if (data) store.set('observations', data.points); } catch (err) { toast(err.message, 'error'); }
  loadIncidents(); // los anillos y huellas siguen la misma ventana de horas
}

function mountChipsControl() {
  if (chipsEl) return;
  const wrap = $('.map-wrap');
  if (!wrap) return;
  chipsEl = document.createElement('div');
  chipsEl.className = 'map-chips';
  chipsEl.id = 'map-chips';
  chipsEl.setAttribute('role', 'group');
  chipsEl.setAttribute('aria-label', 'Filtrar los puntos de calor');
  chipsEl.innerHTML = String(html`${RANGES.map(([h, label, short]) => html`<button type="button" class="chip" data-hours="${h}" aria-pressed="${h === store.get('obsHours')}">${dual(label, short)}</button>`)}
    <button type="button" class="chip" data-reliable aria-pressed="${Boolean(store.get('obsFilter')?.reliable)}">${dual('Solo los más seguros', 'Solo confiables')}</button>`);
  // Al elegir se cierra el desplegable: el cambio se ve de inmediato en el mapa y
  // el punto de la píldora avisa que quedó un filtro distinto al de siempre.
  chipsEl.querySelectorAll('[data-hours]').forEach((b) => b.addEventListener('click', () => { setHoras(Number(b.dataset.hours)); filtrosEl.open = false; }));
  chipsEl.querySelector('[data-reliable]').addEventListener('click', () => {
    const f = store.get('obsFilter');
    store.set('obsFilter', { ...f, reliable: !f.reliable });
    filtrosEl.open = false;
  });
  // «Filtros»: los chips se agrupan en una píldora desplegable igual a «Capas» y
  // «Leyenda» — la fila son tres controles, ya no una tira que ocupa el mapa.
  filtrosEl = document.createElement('details');
  filtrosEl.className = 'map-filters';
  filtrosEl.id = 'map-filters';
  filtrosEl.innerHTML = String(html`<summary><span>Filtros<span class="filters-dot" hidden aria-hidden="true"></span></span></summary>`);
  filtrosEl.addEventListener('toggle', () => {
    // Una sola cosa abierta a la vez, igual que «Capas» y «Leyenda».
    if (!filtrosEl.open) return;
    const capas = $('#map-layers'); if (capas) capas.open = false;
    $('#map-legend')?.classList.remove('legend-open');
    $('#legend-chip')?.setAttribute('aria-expanded', 'false');
  });
  const body = document.createElement('div');
  body.className = 'layers-body';
  body.innerHTML = String(html`<div class="layers-group-title">${dual('Desde cuándo', 'Ventana de detección')}</div>`);
  body.appendChild(chipsEl);
  filtrosEl.appendChild(body);
  const dock = $('#map-ctl') || wrap;
  dock.prepend(filtrosEl);
  syncMapChips();
}

function syncMapChips() {
  if (!chipsEl) return;
  chipsEl.querySelectorAll('[data-hours]').forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.hours) === store.get('obsHours'))));
  chipsEl.querySelector('[data-reliable]')?.setAttribute('aria-pressed', String(Boolean(store.get('obsFilter')?.reliable)));
  // El punto avisa que hay un filtro distinto al de siempre (24 h, sin «seguros»).
  const dot = filtrosEl?.querySelector('.filters-dot');
  if (dot) dot.hidden = store.get('obsHours') === 24 && !store.get('obsFilter')?.reliable;
}

function sourcesHtml(status) {
  if (!status) return html`<p class="small muted">Sin información de las fuentes.</p>`;
  const runs = status.runs || [];
  if (!runs.length) return html`<p class="small muted">Aún no hay ingestas registradas. ${{ interna: 'La primera ocurre al iniciar el servidor.', cron: 'La ingesta corre cada 10 minutos: la primera ocurre en unos minutos.' }[status.ingest_mode] || 'La ingesta automática está apagada (BRASA_SCHEDULER=0).'}</p>`;
  return html`<ul class="list">${runs.map((r) => {
    const products = r.product.split(',');
    const newest = products.map((p) => status.newest_observation?.[p]).filter(Boolean).sort().pop();
    return html`<li><span class="dot" style="background:${r.ok ? 'var(--risk-bajo)' : 'var(--risk-extremo)'}"></span>
      <div class="grow"><b class="small">${products.map((p) => SOURCE_NAMES[p] || p).join(' + ')}</b>
        <div class="tiny muted">${r.ok ? `Consulta correcta ${ago(r.finished_at)} · ${fmtNum(r.n_records)} registros, ${fmtNum(r.n_new)} nuevos` : `Falló ${ago(r.finished_at || r.started_at)}: ${r.message || 'sin detalle'}`}</div>
        <div class="tiny muted">${newest ? `Última detección: ${ago(newest)}` : 'Sin detecciones guardadas'}${r.last_ok_at && !r.ok ? ` · último éxito ${ago(r.last_ok_at)}` : ''}</div></div></li>`;
  })}</ul>
  <p class="tiny muted">GOES llega con ~10–20 min de retraso; VIIRS (NOAA-20/21) pasa sobre Chile unas 2 veces al día por satélite y llega con ~1–3 h de retraso.${status.firms_configured ? '' : ' Sin clave NASA FIRMS, VIIRS/MODIS no se ingieren.'}</p>`;
}

function sourcesBlock() {
  const updated = store.get('status')?.last_ingest_at;
  return html`<p class="small x-plain">${updated ? `BRASA revisa los satélites cada 10 minutos. Última revisión: ${ago(updated)}.` : 'BRASA revisa los satélites cada 10 minutos.'} Un satélite estadounidense (GOES) mira Chile todo el tiempo; otros (VIIRS y MODIS) pasan unas veces al día y ven con más detalle.</p>
    <div class="x-tech">${sourcesHtml(store.get('status'))}</div>`;
}

/** Aviso de hueco de GOES (DET-13): «no vemos fuego» no es «no hay fuego». El umbral viene de /api/status. */
function gapNote() {
  const status = store.get('status');
  if (!status?.goes_gap) return '';
  return html`<div class="callout callout-warn" role="alert"><b>Puede que BRASA no esté viendo todo: faltan barridos del satélite GOES en la última hora.</b>
    Que no aparezca calor no garantiza que no haya fuego.<span class="x-tech"> Faltan ${status.goes_missing} de 6 barridos esperados.</span></div>`;
}

/** MAPA-153: línea punteada de cada lugar guardado al foco confiable más cercano
 *  dentro de su radio de aviso, con la misma distancia y rumbo que ya dice Mi zona.
 *  Sin foco en el radio no se dibuja nada; se apaga junto con «Mis lugares». */
function updatePlaceLines() {
  const places = store.get('places') || [];
  const obs = visibleObservations().filter(isReliable);
  const features = [];
  for (const p of places) {
    if (!Number.isFinite(p.lat) || !Number.isFinite(p.lon) || !Number.isFinite(p.radius_km)) continue;
    let best = null;
    for (const o of obs) {
      const km = haversineKm(p.lat, p.lon, o.lat, o.lon);
      if (km <= p.radius_km && (!best || km < best.km)) best = { o, km };
    }
    if (!best) continue;
    const rumbo = cardinal(bearingDeg(p.lat, p.lon, best.o.lat, best.o.lon));
    features.push({ type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[p.lon, p.lat], [best.o.lon, best.o.lat]] },
      properties: { label: `${fmtNum(best.km, best.km < 10 ? 1 : 0)} km · al ${rumbo}` } });
  }
  setData('place-lines', { type: 'FeatureCollection', features });
}

/** MAPA-154: próxima mirada de GOES = último barrido `ok` de `goes_sweeps` + 10 min.
 *  Pasados 30 min avisa el atraso (como `goes_gap`). Sin llamadas: /api/status ya refresca a 60 s. */
function goesNextLine() {
  const status = store.get('status');
  if (!status || store.get('config')?.goes_enabled === false) return '';
  const sweeps = status.goes_sweeps || [];
  const lastOk = sweeps.find((s) => s.ok && s.started_at);
  const mins = lastOk ? minutesSince(lastOk.started_at) : Infinity;
  const texto = !lastOk || mins > 30
    ? 'El último barrido del satélite GOES tiene más de 30 minutos: la fuente va atrasada.'
    : `El satélite GOES vuelve a mirar en ~${Math.ceil(10 - (mins % 10))} min.`;
  return html`<p class="tiny muted">${texto}<span class="x-tech"> Los polares VIIRS (S-NPP, NOAA-20 y NOAA-21) pasan sobre Chile en la madrugada y a primera hora de la tarde, hora local — ventanas aproximadas; fuente: NASA FIRMS / NOAA.</span></p>`;
}

/** Aviso de recorte (FIX-17): el servidor devuelve solo las detecciones más recientes hasta su tope. */
function truncNote() {
  const limit = store.get('obsTruncated');
  if (!limit) return '';
  return html`<div class="callout callout-warn" role="alert"><b>Se muestran las ${fmtNum(limit)} detecciones más recientes.</b> Acota las horas o los filtros para verlas todas.</div>`;
}

function regionCounts(points) {
  const counts = new Map();
  for (const p of points) {
    const key = p.region || 'Fuera de Chile';
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  // Lo de los países vecinos va al final: a quien vive en Chile le importa primero su región.
  return [...counts.entries()].sort((a, b) => (a[0] === 'Fuera de Chile') - (b[0] === 'Fuera de Chile') || b[1] - a[1]);
}

async function render(container, params) {
  const all = store.get('observations') || [];
  const points = visibleObservations();
  const f = store.get('obsFilter');
  const hours = store.get('obsHours');
  const newest = all.map((o) => o.observed_at).sort().pop();
  const reliable = points.filter(isReliable).length;
  const zones = store.get('config')?.zones || {};
  const regions = regionCounts(points);
  const range = RANGES.find((r) => r[0] === hours);
  const updated = store.get('status')?.last_ingest_at;
  const fires = fireIncidents(points);
  updatePlaceLines();
  const official = (store.get('official')?.fires || []).filter((f) => f.status !== 'extinguido');
  container.innerHTML = String(html`
    <h1 class="view-title">Puntos de calor en Chile</h1>
    <div class="map-search">
      <input type="search" class="input" id="map-search" placeholder="Buscar mi comuna o localidad" aria-label="Buscar una comuna o localidad" autocomplete="off" enterkeyhint="search" />
      <div class="search-results" id="map-search-results" aria-live="polite"></div>
    </div>
    <p class="lede">${dual('Calor visto desde el espacio: puede ser un incendio, una quema o una industria. Toca un punto para saber más.', 'GOES-Este cada 10 min y VIIRS/MODIS en cada pasada. Toca un foco para ver su ficha.')}</p>
    <div id="goes-gap">${gapNote()}</div>
    <div id="goes-next">${goesNextLine()}</div>
    <div id="trunc-note">${truncNote()}</div>
    <div class="chips chips-hours" role="group" aria-label="Desde cuándo">${RANGES.map(([h, label, short]) => html`<button class="chip" data-hours="${h}" aria-pressed="${h === hours}">${dual(label, short)}</button>`)}</div>
    <div class="kpis" style="margin-top:12px">
      <div class="kpi"><small>${dual('puntos de calor', 'detecciones')}</small><strong>${fmtNum(points.length)}</strong><span>${range?.[1].toLowerCase()}</span></div>
      <div class="kpi"><small>${dual('más seguros', 'confiables')}</small><strong>${fmtNum(reliable)}</strong><span>${dual('probablemente fuego', 'conf. media o alta')}</span></div>
      <div class="kpi"><small>el último</small><strong class="kpi-text">${newest ? ago(newest) : '—'}</strong><span>${newest ? fmtDateTime(newest) : 'sin datos'}</span></div>
    </div>
    <div class="switch-row" style="margin-top:6px"><div class="grow"><b class="small">${dual('Ocultar los dudosos', 'Solo detecciones confiables')}</b><div class="tiny muted">${dual('Muestra solo los puntos que más probablemente son fuego.', 'Oculta píxeles de baja confianza (más falsos positivos).')}</div></div>
      <label class="switch"><input type="checkbox" id="f-reliable" aria-label="Ocultar los puntos dudosos" ${f.reliable ? 'checked' : ''} /><span></span></label></div>
    <div class="x-tech"><div class="chips" style="margin-top:6px" role="group" aria-label="Sensores">${Object.entries(SENSOR_LABEL).map(([k, label]) => html`<button class="chip" data-sensor="${k}" aria-pressed="${f.sensors[k] !== false}">${label}</button>`)}</div></div>
    <div class="btn-row" style="margin-top:14px"><button class="btn btn-primary" id="report">Veo humo o fuego</button></div>
    ${official.length ? html`<h2 class="section">${dual('Incendios que informa CONAF', 'CONAF · incendios no extinguidos')} <span class="tag">${official.length}</span></h2>
      <ul class="list">${official.slice(0, 8).map((f) => html`<li><button class="row-btn" data-official="${f.id}"><span class="status-badge st-${OFFICIAL_TONE[f.status]}">${f.status_raw || OFFICIAL_LABEL[f.status]}</span>
        <span class="grow small"><b>${f.name || 'Sin nombre'}</b> · ${f.comuna || ''}</span><span class="tiny muted">${ago(f.started_at)}</span></button></li>`)}</ul>
      <p class="tiny muted">Fuente: <a href="${store.get('official').source.url}" target="_blank" rel="noopener">CONAF, reporte público de incendios</a>. ${dual('Es información oficial.', store.get('official').source.note)}</p>` : ''}
    ${fires.length ? html`<h2 class="section">${dual('Posibles incendios', 'Incidentes con evidencia')} <span class="tag">${fires.length}</span></h2>
      <ul class="list">${fires.slice(0, 8).map((i) => html`<li><a class="row-btn" href="#/incendio/${i.id}"><span class="status-badge st-${incidentInfo(i).tone}">${incidentInfo(i).short}</span>
        <span class="grow small"><b>${i.comuna || dual('En un país vecino', 'Fuera de Chile')}</b> · ${dual(`calor visto ${i.n} veces`, `${i.n} detecciones`)}</span><span class="tiny muted">${ago(i.last)}</span></a></li>`)}</ul>` : ''}
    <h2 class="section">${dual('Dónde hay más', 'Por región')}</h2>
    ${regions.length ? html`<ul class="list">${regions.slice(0, 10).map(([name, n]) => {
      const zone = Object.values(zones).find((z) => z.label === name);
      return html`<li><button class="row-btn" data-zone="${zone ? Object.keys(zones).find((k) => zones[k] === zone) : ''}"><span class="grow small"><b>${name === 'Fuera de Chile' ? dual('En países vecinos', 'Fuera de Chile') : name}</b></span><span class="small tabular">${fmtNum(n)}</span></button></li>`;
    })}</ul>` : !updated && store.get('statusError') ? html`<div id="map-err"></div>` : !updated ? html`<div class="empty"><div class="glyph">◎</div><b>Aún no llegan datos de los satélites.</b> BRASA los revisa cada 10 minutos; vuelve en un rato.</div>` : html`<div class="empty"><div class="glyph">◎</div>No se ve calor en este período. Ojo: que no aparezca no garantiza que no haya fuego (puede haber nubes o humo).</div>`}
    <h2 class="section" id="fuentes">De dónde vienen los datos</h2>
    <div id="sources-block">${sourcesBlock()}</div>
    <div class="x-tech">
    <h2 class="section">Explorar una fecha (NASA FIRMS)</h2>
    <form id="explore" class="card">
      <div class="field"><label for="ex-zone">Zona</label><select class="input" id="ex-zone">${Object.entries(zones).map(([k, z]) => html`<option value="${k}">${z.label}</option>`)}</select></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div class="field"><label for="ex-date">Desde</label><input class="input" type="date" id="ex-date" min="2000-11-01" max="${todayChile()}" value="2024-02-02" aria-describedby="ex-date-hint" /><span class="tiny muted" id="ex-date-hint">Ejemplo: 2 feb 2024, incendio de Viña del Mar.</span></div>
        <div class="field"><label for="ex-days">Días</label><select class="input" id="ex-days">${[1, 2, 3, 5, 7, 10].map((d) => html`<option value="${d}" ${d === 3 ? 'selected' : ''}>${d}</option>`)}</select></div>
      </div>
      <button class="btn btn-block" type="submit">Consultar archivo satelital</button>
      <p class="tiny muted" id="ex-note" style="margin-top:8px">Usa el archivo científico VIIRS/MODIS (o NRT para fechas recientes). Requiere clave FIRMS en el servidor.</p>
    </form></div>
    <p class="tiny muted x-plain" style="margin-top:14px">¿Quieres ver sensores, intensidad y estado técnico de cada fuente? Activa la <b>lectura detallada</b> en Ajustes (Aa).</p>
    <p class="tiny muted" style="margin-top:10px"><a href="/web/respuesta.html">Tiempos de respuesta oficiales de CONAF</a></p>`);

  // Elegir un lugar baja la hoja a «peek» o el vuelo queda tras el panel (MAPA-164).
  bindBuscarComuna(container, () => document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'peek' })));
  container.querySelectorAll('[data-hours]').forEach((b) => b.addEventListener('click', () => setHoras(Number(b.dataset.hours))));
  container.querySelector('#f-reliable').addEventListener('change', (e) => store.set('obsFilter', { ...store.get('obsFilter'), reliable: e.target.checked }));
  container.querySelectorAll('[data-sensor]').forEach((b) => b.addEventListener('click', () => {
    const current = store.get('obsFilter');
    store.set('obsFilter', { ...current, sensors: { ...current.sensors, [b.dataset.sensor]: current.sensors[b.dataset.sensor] === false } });
  }));
  container.querySelectorAll('[data-zone]').forEach((b) => b.addEventListener('click', () => { const z = zones[b.dataset.zone]; if (z) fitBbox(z.bbox); }));
  container.querySelector('#report').addEventListener('click', () => reportForm());
  container.querySelectorAll('[data-official]').forEach((b) => b.addEventListener('click', () => {
    const f = store.get('official').fires.find((x) => x.id === b.dataset.official);
    if (!f) return;
    // MAPA-162: la hoja baja a «peek» antes de volar — con ella desplegada el punto y
    // su ficha quedaban detrás del panel. En escritorio el evento no mueve nada.
    document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'peek' }));
    fly(f.lon, f.lat, 11.5);
    popupOficial(f, [f.lon, f.lat]);
  }));
  container.querySelector('#explore').addEventListener('submit', (e) => { e.preventDefault(); explore(container); });
  // UX-77: sin datos por falla de carga (la API caída deja el panel vacío), el bloque
  // compartido muestra los teléfonos de emergencia y «Reintentar».
  const errHost = container.querySelector('#map-err');
  if (errHost) errorConSalida(errHost, store.get('statusError'), () => {
    loadOfficial();
    loadIncidents();
    loadObservations().then((d) => { if (d) store.set('observations', d.points); }).catch(() => {});
  });
  if (params?.panel === 'fuentes') container.querySelector('#fuentes')?.scrollIntoView();
}

async function explore(container) {
  const zone = container.querySelector('#ex-zone').value;
  const start = container.querySelector('#ex-date').value;
  const days = container.querySelector('#ex-days').value;
  const note = container.querySelector('#ex-note');
  note.textContent = 'Consultando NASA FIRMS…';
  try {
    const data = await api.explore({ zone, mode: 'historical', start, days });
    setData('explore', pointsGeoJSON(data.points, (p) => ({ id: p.id })));
    show('explore', true);
    const zones = store.get('config').zones;
    fitBbox(zones[zone].bbox);
    note.textContent = `${fmtNum(data.points.length)} detecciones (${fmtNum(data.in_chile)} en Chile) entre ${data.start} y ${data.end} · ${data.sources.join(', ')}. ${data.notices.join(' ')}`;
    openModal(html`<h2 id="modal-title">Archivo satelital cargado</h2><p>${fmtNum(data.points.length)} detecciones en amarillo sobre el mapa.</p>
      <p class="small muted">Para ver un incendio paso a paso, con gráficos y clima, usa la sección <a href="#/casos">Casos</a>.</p>`);
  } catch (err) {
    note.textContent = err.message;
  }
}

function applyLayers() {
  show(['detections', 'goes-pixels'], layers.focos);
  show('official', layers.incendios);
  show('risk-fill', layers.risk);
  show('rain-fill', layers.rain);
  show('reports', layers.reports);
  show(['places', 'place-radius-fill', 'place-radius-line'], layers.places);
  show('incident-hulls-fill', layers.hulls); // el contorno (hulls-line) sigue a «Focos de calor» desde zoom 7 (MAPA-163)
  show('lightning', layers.lightning);
  show(['scars-fill', 'scars-line'], layers.scars);
  show('smoke-fill', layers.aire);
  show('senapred-fill', layers.senapred);
  show('viento', layers.viento); // canvas propio: la visibilidad solo alimenta el resumen
  setRelieve(layers.relieve);
}

let unsubs = [];
export default {
  id: 'mapa',
  sheet: 'peek',
  async mount(container, { params }) {
    mounted = true;
    // Vista compartible: #/mapa?capas=focos,riesgo fija las capas del control.
    const fromUrl = capasFromUrl(params?.capas);
    if (fromUrl) Object.assign(layers, fromUrl);
    show(['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event'], false);
    applyLayers();
    mountLayersControl();
    mountChipsControl();
    syncCapaInputs();
    legend();
    $('#map-legend').classList.add('mobile-show');
    bindMap();
    loadReports();
    loadOfficial().then(() => mounted && keepPlace(container, () => render(container, {})));
    if (layers.risk || layers.rain) loadRisk();
    loadIncidents();
    if (layers.scars) loadScars();
    if (layers.senapred) loadSenapred();
    if (layers.aire) loadSmoke().then(() => { if (mounted) { syncCapaInputs(); legend(); } });
    if (layers.viento) loadWind().then(() => { if (mounted) { syncCapaInputs(); legend(); } });
    if (params?.lat && params?.lon) fly(Number(params.lon), Number(params.lat), Number(params.z) || 11);
    await render(container, params);
    ultimoRefrescoIncidentes = Date.now(); // incidentes y CONAF recién cargados arriba
    // Datos nuevos: se redibuja el panel sin perder el lugar. El estado de las fuentes solo toca su bloque.
    unsubs = ['observations', 'obsFilter', 'places'].map((k) => store.on(k, () => mounted && keepPlace(container, () => render(container, {}))));
    // MAPA-164: la fila de chips y el aviso de fondo sin conexión viven fuera del
    // panel — no se repintan con render, así que cada uno tiene su suscripción.
    unsubs.push(store.on('obsHours', () => mounted && syncMapChips()));
    unsubs.push(store.on('obsFilter', () => mounted && syncMapChips()));
    unsubs.push(store.on('basemapOffline', () => mounted && syncCapaInputs()));
    // MAPA-163: el mismo lote refresca incidentes y CONAF (con tope y solo visible).
    unsubs.push(store.on('observations', alLlegarObservaciones));
    // MAPA-165: enlaces de «Compartir» (foco=/conaf=) abren la ficha cuando su dato llega.
    pendienteFoco = params?.foco;
    pendienteConaf = params?.conaf;
    intentarEnlace();
    unsubs.push(store.on('observations', intentarEnlace));
    unsubs.push(store.on('official', intentarEnlace));
    unsubs.push(store.on('status', () => {
      const el = mounted && container.querySelector('#sources-block');
      if (el) el.innerHTML = String(sourcesBlock());
      const gap = mounted && container.querySelector('#goes-gap');
      if (gap) gap.innerHTML = String(gapNote());
      const next = mounted && container.querySelector('#goes-next');
      if (next) next.innerHTML = String(goesNextLine());
    }));
  },
  unmount() {
    mounted = false;
    pendienteFoco = pendienteConaf = null;
    unsubs.forEach((u) => u());
    // El viento dibuja en un canvas aparte de MapLibre: apagarlo exige apagar() —
    // show() solo cambia el resumen. layers.viento se conserva: al volver, mount()
    // lo recarga si seguía prendido.
    if (layers.viento) import('../viento.js').then((m) => m.apagar());
    cerrarPopup();
    soltar.forEach((s) => s());
    soltar = [];
    // Las demás vistas ven los focos sueltos; lo opcional de esta vista queda apagado.
    show(['detections', 'goes-pixels'], true);
    show(['explore', 'official', 'incident-hulls-fill', 'incident-hulls-line', 'incident-labels', 'scars-fill', 'scars-line', 'smoke-fill',
      'risk-fill', 'rain-fill', 'senapred-fill', 'lightning', 'viento', 'relieve-hillshade'], false);
    setData('place-lines', EMPTY_FC);
    layersEl?.remove();
    layersEl = null;
    chipsEl?.remove();
    chipsEl = null;
    $('#map-legend').classList.remove('mobile-show');
  },
};
