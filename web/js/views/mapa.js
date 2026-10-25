/* Mapa en vivo: focos de calor GOES + VIIRS/MODIS, capas, fuentes y exploración histórica FIRMS. */
import { api, request } from '../api.js';
import { buscarComunas } from '../buscador.js';
import { CAPAS, capasFromUrl, capasToUrl, senapredPorComuna, toggleCapa } from '../capas.js';
import { AGE_BINS, basemap, BASEMAPS, EMPTY_FC, fitBbox, fly, getMap, LIGHTNING_COLOR, pointsGeoJSON, RAIN_COLORS, RISK_COLORS, SENAPRED_COLORS, setBasemap, setData, setRain, setRelieve, setRisk, setSenapred, show, SMOKE_COLOR } from '../map.js';
import { isReliable, loadObservations, visibleObservations } from '../data.js';
import { store } from '../store.js';
import { incidentInfo } from './incendio.js';
import { testigos } from '../reportes.js';
import { openModal, placeForm, reportForm } from '../ui.js';
import { $, ago, bearingDeg, cardinal, dual, fmtDateTime, fmtNum, fmtUTC, haversineKm, html, keepPlace, minutesSince, RISK, SENSOR_LABEL, toast, todayChile } from '../util.js';

const RANGES = [[6, 'Últimas 6 horas', '6 h'], [24, 'Hoy', '24 h'], [48, '2 días', '48 h'], [168, 'Semana', '7 días']];
const SOURCE_NAMES = {
  GOES19_FDCF: 'GOES-19 · cada 10 min', GOES16_FDCF: 'GOES-16', VIIRS_NOAA20_NRT: 'VIIRS NOAA-20', VIIRS_NOAA21_NRT: 'VIIRS NOAA-21',
  VIIRS_SNPP_NRT: 'VIIRS Suomi NPP', MODIS_NRT: 'MODIS Terra/Aqua',
};
let mounted = false;
let handlers = [];
let popup = null;
let layersEl = null;
let smokeMeta = null;
// Alertas SENAPRED de la capa nacional (OFI-207): {code: [alertas]} para el popup y la
// marca de la última descarga que informa el endpoint.
let senapredPorCode = {};
let senapredFetchedAt = null;
// Capas cuya primera carga es diferida: mientras llegan, la casilla sigue enfocable (MAPA-141).
const cargando = new Set();
const layers = { focos: true, incendios: true, risk: false, rain: false, reports: true, places: true, hulls: false, lightning: false, aire: false, scars: false, senapred: false, relieve: false };
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
  $('#map-legend').innerHTML = String(html`${layers.focos ? html`<div class="legend-title">¿Hace cuánto se vio el calor?</div>
    <div class="legend-row">${AGE_BINS.map((b) => html`<span class="legend-item"><span class="sw" style="background:${b.color}"></span>${b.label}</span>`)}</div>` : ''}
    ${layers.focos || layers.incendios || layers.reports ? html`<div class="legend-row" style="margin-top:4px">
      ${layers.focos ? html`<span class="legend-item"><span class="sw sw-sq" style="background:#ff7a2e;opacity:.6"></span>${dual('Zona de unos 2 km', 'Píxel GOES (~2–3 km)')}</span>
      <span class="legend-item"><span class="sw" style="background:#ff7a2e"></span>${dual('Punto más preciso', 'VIIRS/MODIS')}</span>` : ''}
      ${layers.incendios ? html`<span class="legend-item"><span class="sw sw-ring"></span>${dual('Incendio que informa CONAF', 'Incendio CONAF (oficial)')}</span>` : ''}
      ${layers.reports ? html`<span class="legend-item"><span class="sw" style="background:#6250d6"></span>Aviso de vecino revisado</span>` : ''}</div>` : ''}
    ${layers.focos ? html`<div class="legend-note">${dual('El tamaño sube con la potencia del calor. De lejos los focos se agrupan: el número cuenta focos de calor, no incendios. El anillo de colores es un posible incendio: tócalo para ver su ficha.', 'Radio por FRP; bajo zoom 7 decimación por celda con conteo, más un anillo por incidente abierto (color = estado) que abre #/incendio/<id>.')}</div>` : ''}
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
    ${layers.focos ? html`<div class="legend-note">${dual('Calor no siempre es incendio. Los puntos pálidos son dudosos.', 'Un foco de calor no confirma un incendio. Los puntos tenues tienen confianza baja.')}</div>` : ''}`);
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

const OFFICIAL_LABEL = { confirmado: 'En curso', controlado: 'Controlado', extinguido: 'Extinguido' };
const OFFICIAL_TONE = { confirmado: 'urgente', controlado: 'aviso', extinguido: 'tranquilo' };

async function loadOfficial() {
  try {
    const data = await api.officialFires();
    if (!mounted) return;
    store.set('official', data);
    setData('official', pointsGeoJSON(data.fires, (f) => ({ id: f.id, status: f.status })));
  } catch { /* sin conexión: se mantiene lo último */ }
}

function officialPopup(fire, lngLat) {
  popup?.remove();
  popup = new maplibregl.Popup({ maxWidth: '280px', offset: 10 }).setLngLat(lngLat).setHTML(String(html`<div style="max-width:250px">
    <div class="tiny">Incendio informado por CONAF</div>
    <b>${fire.name || 'Sin nombre'}</b> · <span class="status-badge st-${OFFICIAL_TONE[fire.status]}">${fire.status_raw || OFFICIAL_LABEL[fire.status]}</span>
    <div class="small" style="margin-top:4px">${fire.comuna ? `${fire.comuna}, ${fire.region}` : ''}</div>
    <div class="small">Empezó ${ago(fire.started_at)} · ${fmtDateTime(fire.started_at)}${fire.area_ha ? ` · ${fmtNum(fire.area_ha, fire.area_ha < 10 ? 1 : 0)} ha` : ''}</div>
    <div class="tiny muted" style="margin-top:6px">${dual('Así lo informa CONAF. Sigue a SENAPRED y a tu municipio.', `Fuente: CONAF (GEPRIF), reporte público. Ámbito ${fire.ambito || 'n/d'}${fire.fuel ? ` · combustible inicial: ${fire.fuel}` : ''}.`)}</div></div>`)).addTo(getMap());
}

function detailPopup(obs, lngLat) {
  const age = ago(obs.observed_at);
  const reliable = ['alta', 'nominal', 'media'].includes(obs.confidence);
  const content = html`<div style="max-width:250px">
    <b>Punto de calor</b> · <span class="muted">visto ${age}</span>
    <div class="small" style="margin-top:4px">${obs.comuna ? `${obs.comuna}, ${obs.region}` : 'Fuera del territorio chileno'}</div>
    <p class="small x-plain" style="margin:8px 0 0">${obs.sensor === 'ABI' ? 'Lo vio un satélite que mira Chile cada 10 minutos. Marca una zona de unos 2 km: el calor está en algún punto dentro del cuadro.' : 'Lo vio un satélite que pasa sobre Chile unas veces al día. Su ubicación es bastante precisa.'}
      ${reliable ? 'Puede ser un incendio, una quema o una industria.' : 'Es una señal dudosa: puede no ser fuego.'}</p>
    <div class="x-tech small" style="margin-top:6px">
      <div>${SENSOR_LABEL[obs.sensor] || obs.sensor} · <b>${obs.satellite || obs.source}</b></div>
      <div>${fmtDateTime(obs.observed_at)} Chile · ${fmtUTC(obs.observed_at)}</div>
      <div>FRP ${obs.frp_mw != null ? `${fmtNum(obs.frp_mw, 1)} MW` : 'n/d'} · confianza ${obs.confidence || 'n/d'} · ${obs.sensor === 'ABI' ? 'píxel ~2–3 km' : `píxel ${obs.resolution_m || 375} m`}</div>
      <div class="tabular">${obs.lat.toFixed(4)}, ${obs.lon.toFixed(4)}</div></div>
    ${obs.incident_id && obs.incident_n > 1 ? html`<p class="small" style="margin:8px 0 0"><b>${incidentInfo({ status: obs.incident_status, fixed_source: obs.incident_fixed }).title}</b> · ${dual(`se vio calor ${obs.incident_n} veces aquí`, `${obs.incident_n} detecciones agrupadas`)}</p>
      <a class="btn btn-sm btn-primary" style="margin-top:6px" href="#/incendio/${obs.incident_id}">Ver qué ha pasado aquí</a>` : ''}
    <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm" id="pp-watch">Avisarme si hay más aquí</button><button class="btn btn-sm btn-ghost" id="pp-report">Contar lo que veo</button></div></div>`;
  popup?.remove();
  popup = new maplibregl.Popup({ maxWidth: '280px', offset: 10 }).setLngLat(lngLat).setHTML(String(content)).addTo(getMap());
  const el = popup.getElement();
  el.querySelector('#pp-watch').addEventListener('click', () => { popup.remove(); placeForm(null, { lat: obs.lat, lon: obs.lon }); });
  el.querySelector('#pp-report').addEventListener('click', () => { popup.remove(); reportForm({ lat: obs.lat, lon: obs.lon }); });
}

function bindMap() {
  const map = getMap();
  const onDetection = (e) => {
    const props = e.features?.[0]?.properties;
    // Una celda agrupa varios focos (MAPA-01): tocarla acerca hasta separarlos, no abre ficha.
    if (props?.count > 1) {
      map.easeTo({ center: e.lngLat, zoom: Math.min(map.getZoom() + 1.8, 10.5), duration: 600 });
      return;
    }
    const obs = (store.get('observations') || []).find((o) => o.id === props?.id);
    if (obs) detailPopup(obs, e.lngLat);
  };
  const onReport = (e) => {
    const p = e.features[0].properties;
    popup?.remove();
    popup = new maplibregl.Popup({ maxWidth: '280px' }).setLngLat(e.lngLat).setHTML(String(html`<div class="tiny">Aviso de un vecino, revisado por BRASA</div>
      <b>${p.kind_label}</b> · <span class="muted">${ago(p.created_at)}</span><p class="small" style="margin-top:6px">${p.description || 'Sin descripción.'}</p>
      ${p.has_photo ? html`<img class="photo" alt="Foto del reporte" src="/api/reports/${p.id}/photo" />` : ''}
      ${testigos(p) ? html`<div class="tiny">${testigos(p)}</div>` : ''}
      <div class="tiny muted">Lo revisó un voluntario de BRASA. No es información oficial.</div>`)).addTo(map);
  };
  const onRisk = (e) => {
    if (!layers.risk) return;
    const props = e.features[0].properties;
    const r = store.get('risk')?.comunas?.[props.code];
    popup?.remove();
    popup = new maplibregl.Popup({ maxWidth: '260px' }).setLngLat(e.lngLat).setHTML(String(html`<b>${props.name}</b><div class="tiny muted">${props.region}</div>
      <div style="margin-top:6px">${r ? html`<span class="risk-chip ${RISK[r.level].cls}">Peligro ${RISK[r.level].label.toLowerCase()}</span>
      <p class="small" style="margin:6px 0 0">${RISK[r.level].plain}</p>
      <div class="small muted" style="margin-top:4px">Hasta ${fmtNum(r.tmax)} °C · humedad ${fmtNum(r.rhmin)} % · viento ${fmtNum(r.windmax)} km/h</div>` : 'Aún sin pronóstico.'}</div>
      <a class="btn btn-sm" style="margin-top:8px" href="#/riesgo?comuna=${props.code}">Ver los próximos días</a>`)).addTo(map);
  };
  const onRain = (e) => {
    if (!layers.rain) return;
    const props = e.features[0].properties;
    const r = store.get('risk')?.rain?.[props.code];
    popup?.remove();
    popup = new maplibregl.Popup({ maxWidth: '260px' }).setLngLat(e.lngLat).setHTML(String(html`<b>${props.name}</b><div class="tiny muted">${props.region}</div>
      <div style="margin-top:6px">${r ? html`<b class="small">${r.label}</b>
      <p class="small" style="margin:6px 0 0">${r.plain}</p>
      <div class="small muted" style="margin-top:4px">${fmtNum(r.current_mm)} mm desde junio · lo normal son ${fmtNum(r.normal_mm)} mm</div>` : 'Aún sin dato de lluvia para esta comuna.'}</div>`)).addTo(map);
  };
  const onSenapred = (e) => {
    if (!layers.senapred) return;
    const props = e.features[0].properties;
    const alertas = senapredPorCode[props.code] || [];
    popup?.remove();
    popup = new maplibregl.Popup({ maxWidth: '280px' }).setLngLat(e.lngLat).setHTML(String(html`<b>${props.name}</b><div class="tiny muted">${props.region}</div>
      ${alertas.map((a) => html`<div style="margin-top:8px"><span class="status-badge${SENAPRED_TONO[a.tipo] ? ` st-${SENAPRED_TONO[a.tipo]}` : ''}">${SENAPRED_TITULO[a.tipo] || 'Alerta oficial'}</span>
        <p class="small" style="margin:4px 0 0">${a.title}</p>
        <div class="tiny muted" style="margin-top:4px">${a.issued_at ? fmtDateTime(a.issued_at) : ''} · <a href="${a.url}" target="_blank" rel="noopener">Ver en SENAPRED</a></div></div>`)}
      ${alertas.length ? '' : html`<p class="small" style="margin-top:6px">Ninguna alerta vigente nombra esta comuna.</p>`}
      <div class="tiny muted" style="margin-top:8px">Texto oficial de SENAPRED. BRASA no emite alertas.</div>`)).addTo(map);
  };
  const onIncidentRing = (e) => {
    const id = e.features?.[0]?.properties?.id;
    if (id) location.hash = `#/incendio/${id}`;
  };
  const onOfficial = (e) => {
    const id = e.features?.[0]?.properties?.id;
    const fire = store.get('official')?.fires?.find((f) => f.id === id);
    if (fire) officialPopup(fire, e.lngLat);
  };
  const onLightning = (e) => {
    if (!layers.lightning) return;
    const p = e.features[0].properties;
    popup?.remove();
    popup = new maplibregl.Popup({ maxWidth: '260px' }).setLngLat(e.lngLat).setHTML(String(html`
      <div class="tiny">Rayo visto por el satélite GOES-19</div>
      <b>${ago(p.observed_at)}</b> · <span class="muted">${fmtDateTime(p.observed_at)}</span>
      ${p.energy_j ? html`<div class="small" style="margin-top:4px">Energía ${fmtNum(p.energy_j)} J${p.area_km2 ? ` · área ~${fmtNum(p.area_km2)} km²` : ''}</div>` : ''}
      <div class="tiny muted" style="margin-top:6px">Un rayo no es un incendio: es luz de tormenta vista desde el espacio.</div>`)).addTo(map);
  };
  const onScars = (e) => {
    if (!layers.scars) return;
    const p = e.features[0].properties;
    popup?.remove();
    popup = new maplibregl.Popup({ maxWidth: '260px' }).setLngLat(e.lngLat).setHTML(String(html`<b>${p.comuna}</b><div class="tiny muted">${p.region}</div>
      <div class="small" style="margin-top:6px">${dual(`El satélite vio calor aquí esta temporada: unas ${fmtNum(p.ha)} ha en ${p.n_incidentes} ${p.n_incidentes === 1 ? 'incidente' : 'incidentes'}.`, `Huella de detecciones: ${fmtNum(p.ha)} ha · ${p.n_incidentes} ${p.n_incidentes === 1 ? 'incidente' : 'incidentes'} · ${p.desde?.slice(0, 10)} a ${p.hasta?.slice(0, 10)}.`)}</div>
      <div class="tiny muted" style="margin-top:6px">${dual('No es el perímetro oficial del incendio: es la zona donde se observó calor.', 'Fuente: huella BRASA de detecciones satelitales, no CONAF.')}</div>`)).addTo(map);
  };
  for (const [layer, fn] of [['detections', onDetection], ['goes-pixels', onDetection], ['reports', onReport], ['risk-fill', onRisk], ['rain-fill', onRain], ['senapred-fill', onSenapred], ['official', onOfficial], ['incident-rings', onIncidentRing], ['lightning', onLightning], ['scars-fill', onScars]]) {
    map.on('click', layer, fn);
    handlers.push([layer, fn]);
  }
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

/** Incidentes abiertos desde /api/incidents: alimenta los anillos a escala país
 *  (MAPA-152, parte de la capa «Focos de calor») y, con la capa prendida, las
 *  huellas aproximadas (DET-10). Las anomalías no son incendios: no llevan anillo. */
const RING_STATUS = new Set(['posible', 'reportado', 'confirmado', 'controlado']);
async function loadIncidents() {
  try {
    const data = await api.incidents(store.get('obsHours'), layers.hulls);
    if (!mounted) return;
    if (layers.hulls) {
      const features = data.incidents.filter((i) => i.hull)
        .map((i) => ({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [i.hull] }, properties: { id: i.id, status: i.status } }));
      setData('incident-hulls', { type: 'FeatureCollection', features });
    }
    setData('incident-rings', pointsGeoJSON(
      data.incidents.filter((i) => RING_STATUS.has(i.status)),
      (i) => ({ id: i.id, status: i.status, n: i.n_obs })));
  } catch (err) { toast(err.message, 'error'); }
}

/** Destellos GLM de la última hora, solo al encender el switch. Si el conjunto no está
 *  disponible (503 u otro fallo), el switch vuelve a apagado y el mapa sigue igual. */
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
    toast(err instanceof TypeError ? 'Sin conexión con el servidor: no se pudieron cargar los rayos.' : err.message, 'error');
  }
}

/** Alertas oficiales vigentes de SENAPRED para la capa nacional (OFI-207): pinta las
 *  comunas que cada título nombra, con la clase más grave por comuna. Como los rayos y el
 *  humo, un fallo devuelve el switch a apagado; la fuente ya degrada a `[]` por su cuenta. */
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

/** Humo GOES-19 (capa «aire», DET-16): manchas de aerosol de la última hora. Se carga al
 *  encender y, si no está, el switch vuelve a apagado (mismo patrón que los rayos). */
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
  document.querySelectorAll('#view [data-layer]').forEach((i) => { i.checked = Boolean(layers[i.dataset.layer]); });
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
  if (checked && lazy && !cargando.has(key)) {
    cargando.add(key);
    try { await lazy(input); } finally { cargando.delete(key); }
  }
  if (key === 'aire' && !checked) setData('smoke', EMPTY_FC);
  if (key === 'viento') show('viento', checked); // canvas propio: solo registra la visibilidad para el resumen
  if (key === 'viento' && !checked) { vientoEdadTxt = ''; import('../viento.js').then((m) => m.apagar()); legend(); }
  if (key === 'lightning' && !checked) setData('lightning', EMPTY_FC);
  applyLayers();
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

/** Control compacto sobre el mapa: un `<details>` con todas las capas conmutables.
 *  Los checkboxes son operables con teclado; el estado se anuncia vía #capas-live. */
function mountLayersControl() {
  if (layersEl) return;
  const wrap = $('.map-wrap');
  if (!wrap) return;
  layersEl = document.createElement('details');
  layersEl.className = 'map-layers';
  layersEl.id = 'map-layers';
  // El anuncio va dentro del <summary>: el resto del <details> cerrado no se renderiza.
  layersEl.innerHTML = String(html`<summary><span>Capas</span><span class="layers-count" aria-hidden="true"></span><span class="sr-only" id="capas-live" role="status"></span></summary>
    <div class="layers-body">
      <div class="map-search">
        <input type="search" class="input" id="map-search" placeholder="Buscar mi comuna" aria-label="Buscar una comuna" autocomplete="off" />
        <div class="search-results" id="map-search-results" aria-live="polite"></div>
      </div>
      <div role="group" aria-label="Capas del mapa">${CAPAS.map((c) => html`
        <div class="switch-row"><div class="grow"><b class="small">${c.label}</b></div>
          <label class="switch"><input type="checkbox" data-capa="${c.key}" aria-label="${c.aria}" /><span></span></label></div>`)}
      </div>
    </div>`);
  wrap.insertBefore(layersEl, wrap.querySelector('.map-legend'));
  layersEl.querySelectorAll('[data-capa]').forEach((input) => input.addEventListener('change', () => setCapa(input.dataset.capa, input.checked, input)));

  const search = layersEl.querySelector('#map-search');
  const results = layersEl.querySelector('#map-search-results');
  let hits = [];
  let turno = 0;
  const pintar = async () => {
    const mio = ++turno;
    const index = await loadComunasIndex();
    if (mio !== turno) return;
    hits = buscarComunas(index, search.value);
    results.innerHTML = hits.length
      ? String(html`${hits.map((c) => html`<button type="button" class="search-hit" data-code="${c.code}"><span>${c.name}</span><span class="tiny">${c.region}</span></button>`)}`)
      : search.value.trim() ? '<p class="tiny muted">No encontramos esa comuna.</p>' : '';
  };
  const elegir = (code) => {
    const comuna = hits.find((c) => String(c.code) === code);
    if (!comuna) return;
    const [lon, lat] = comuna.center;
    fly(lon, lat, comuna.bbox ? zoomParaBbox(comuna.bbox) : 10);
    layersEl.open = false;
    search.value = '';
    results.innerHTML = '';
    layersEl.querySelector('summary')?.focus();
  };
  search.addEventListener('focus', pintar);
  search.addEventListener('input', pintar);
  search.addEventListener('search', pintar);
  results.addEventListener('click', (e) => {
    const boton = e.target.closest('[data-code]');
    if (boton) elegir(boton.dataset.code);
  });
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

/** MAPA-154: cuándo vuelve a mirar GOES — último barrido `ok` de `goes_sweeps` más la
 *  cadencia de 10 min del disco completo. Con más de 30 min de atraso lo dice, como
 *  el aviso `goes_gap`. Sin llamadas nuevas: /api/status ya se refresca cada 60 s. */
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
    <p class="lede">${dual('Calor visto desde el espacio: puede ser un incendio, una quema o una industria. Toca un punto para saber más.', 'GOES-Este cada 10 min y VIIRS/MODIS en cada pasada. Toca un foco para ver su ficha.')}</p>
    <div id="goes-gap">${gapNote()}</div>
    <div id="goes-next">${goesNextLine()}</div>
    <div id="trunc-note">${truncNote()}</div>
    <div class="chips" role="group" aria-label="Desde cuándo">${RANGES.map(([h, label, short]) => html`<button class="chip" data-hours="${h}" aria-pressed="${h === hours}">${dual(label, short)}</button>`)}</div>
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
    })}</ul>` : !updated ? html`<div class="empty"><div class="glyph">◎</div><b>Aún no llegan datos de los satélites.</b> BRASA los revisa cada 10 minutos; vuelve en un rato.</div>` : html`<div class="empty"><div class="glyph">◎</div>No se ve calor en este período. Ojo: que no aparezca no garantiza que no haya fuego (puede haber nubes o humo).</div>`}
    <h2 class="section">Qué mostrar en el mapa</h2>
    <div class="segmented" role="group" aria-label="Fondo del mapa">${Object.entries(BASEMAPS).map(([k, b]) => html`<button data-basemap="${k}" aria-pressed="${basemap() === k}">${b.label}</button>`)}</div>
    ${store.get('basemapOffline') ? html`<p class="tiny muted" style="margin-top:6px">El fondo del mapa no carga ahora; se muestran solo los límites de las comunas.</p>` : ''}
    <div style="margin-top:8px">
      <div class="switch-row"><div class="grow"><b class="small">Focos de calor</b><div class="tiny muted">${dual('Los puntos de calor de los satélites.', 'Detecciones GOES-19 + VIIRS/MODIS.')}</div></div><label class="switch"><input type="checkbox" data-layer="focos" aria-label="Mostrar los focos de calor" ${layers.focos ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Incendios de CONAF</b><div class="tiny muted">${dual('Los que informa CONAF.', 'Reporte público de incendios de CONAF (GEPRIF).')}</div></div><label class="switch"><input type="checkbox" data-layer="incendios" aria-label="Mostrar los incendios que informa CONAF" ${layers.incendios ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Peligro de incendio hoy</b><div class="tiny muted">${dual('Pinta cada comuna según el clima de hoy.', 'Índice 30-30-30 diario por comuna (Open-Meteo).')}</div></div><label class="switch"><input type="checkbox" data-layer="risk" aria-label="Mostrar el peligro de incendio de hoy" ${layers.risk ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Humo en el aire</b><div class="tiny muted">${dual('Las plumas que ve el satélite. No son incendios.', 'Manchas de aerosol de GOES-19 (ABI-L2-ADPF), últimos 60 min.')}</div></div><label class="switch"><input type="checkbox" data-layer="aire" aria-label="Mostrar el humo que ve el satélite" ${layers.aire ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Lluvia de la temporada</b><div class="tiny muted">${dual('¿Dónde ha llovido menos que un año normal?', 'Junio–hoy vs. normal 1991-2020 (Open-Meteo)')}</div></div><label class="switch"><input type="checkbox" data-layer="rain" aria-label="Mostrar la lluvia de la temporada" ${layers.rain ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Alertas de SENAPRED</b><div class="tiny muted">${dual('Las comunas que una alerta oficial nombra.', 'Comunas nombradas por alertas vigentes de SENAPRED.')}</div></div><label class="switch"><input type="checkbox" data-layer="senapred" aria-label="Mostrar las alertas de SENAPRED" ${layers.senapred ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Cicatrices de la temporada</b><div class="tiny muted">${dual('Zonas donde el satélite vio calor en los últimos meses.', 'Unión de huellas de detecciones por comuna (90 días). No es el perímetro oficial de CONAF.')}</div></div><label class="switch"><input type="checkbox" data-layer="scars" aria-label="Mostrar las cicatrices de la temporada" ${layers.scars ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Avisos de vecinos</b><div class="tiny muted">Solo los revisados por un voluntario.</div></div><label class="switch"><input type="checkbox" data-layer="reports" aria-label="Mostrar avisos de vecinos" ${layers.reports ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Mis lugares</b></div><label class="switch"><input type="checkbox" data-layer="places" aria-label="Mostrar mis lugares" ${layers.places ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Huellas de calor</b><div class="tiny muted">${dual('El contorno de lo que vieron los satélites en cada posible incendio.', 'Huella aproximada por incidente abierto (≥3 detecciones).')}</div></div><label class="switch"><input type="checkbox" data-layer="hulls" aria-label="Mostrar las huellas de calor" ${layers.hulls ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Rayos de la última hora</b><div class="tiny muted">${dual('Destellos de tormenta que vio el satélite. No son incendios.', 'Destellos GLM de GOES-19, últimos 60 min.')}</div></div><label class="switch"><input type="checkbox" data-layer="lightning" aria-label="Mostrar los rayos de la última hora" ${layers.lightning ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Relieve</b><div class="tiny muted">${dual('Los cerros y quebradas sombreados.', 'Sombreado de relieve (Copernicus DEM GLO-30, ~30 m).')}</div></div><label class="switch"><input type="checkbox" data-layer="relieve" aria-label="Mostrar el relieve sombreado" ${layers.relieve ? 'checked' : ''} /><span></span></label></div>
    </div>
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
    <p class="tiny muted x-plain" style="margin-top:14px">¿Quieres ver sensores, intensidad y estado técnico de cada fuente? Activa la <b>lectura detallada</b> en Ajustes (Aa).</p>`);

  container.querySelectorAll('[data-hours]').forEach((b) => b.addEventListener('click', async () => {
    store.set('obsHours', Number(b.dataset.hours));
    try { const data = await loadObservations(); if (data) store.set('observations', data.points); } catch (err) { toast(err.message, 'error'); }
    loadIncidents(); // los anillos y huellas siguen la misma ventana de horas
  }));
  container.querySelector('#f-reliable').addEventListener('change', (e) => store.set('obsFilter', { ...store.get('obsFilter'), reliable: e.target.checked }));
  container.querySelectorAll('[data-sensor]').forEach((b) => b.addEventListener('click', () => {
    const current = store.get('obsFilter');
    store.set('obsFilter', { ...current, sensors: { ...current.sensors, [b.dataset.sensor]: current.sensors[b.dataset.sensor] === false } });
  }));
  container.querySelectorAll('[data-zone]').forEach((b) => b.addEventListener('click', () => { const z = zones[b.dataset.zone]; if (z) fitBbox(z.bbox); }));
  container.querySelectorAll('[data-basemap]').forEach((b) => b.addEventListener('click', () => { setBasemap(b.dataset.basemap); render(container, params); }));
  container.querySelectorAll('[data-layer]').forEach((input) => input.addEventListener('change', () => setCapa(input.dataset.layer, input.checked, input)));
  container.querySelector('#report').addEventListener('click', () => reportForm());
  container.querySelectorAll('[data-official]').forEach((b) => b.addEventListener('click', () => {
    const f = store.get('official').fires.find((x) => x.id === b.dataset.official);
    if (f) { fly(f.lon, f.lat, 11.5); officialPopup(f, [f.lon, f.lat]); }
  }));
  container.querySelector('#explore').addEventListener('submit', (e) => { e.preventDefault(); explore(container); });
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
  show(['incident-hulls-fill', 'incident-hulls-line'], layers.hulls);
  show('lightning', layers.lightning);
  show(['scars-fill', 'scars-line'], layers.scars);
  show('smoke-fill', layers.aire);
  show('senapred-fill', layers.senapred);
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
    // Datos nuevos: se redibuja el panel sin perder el lugar. El estado de las fuentes solo toca su bloque.
    unsubs = ['observations', 'obsFilter', 'places', 'basemapOffline'].map((k) => store.on(k, () => mounted && keepPlace(container, () => render(container, {}))));
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
    unsubs.forEach((u) => u());
    popup?.remove();
    const map = getMap();
    handlers.forEach(([layer, fn]) => map.off('click', layer, fn));
    handlers = [];
    // Las demás vistas ven los focos sueltos; lo opcional de esta vista queda apagado.
    show(['detections', 'goes-pixels'], true);
    show(['explore', 'official', 'incident-hulls-fill', 'incident-hulls-line', 'scars-fill', 'scars-line', 'smoke-fill'], false);
    setData('place-lines', EMPTY_FC);
    layersEl?.remove();
    layersEl = null;
    $('#map-legend').classList.remove('mobile-show');
  },
};
