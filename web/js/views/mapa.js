/* Mapa en vivo: focos de calor GOES + VIIRS/MODIS, capas, fuentes y exploración histórica FIRMS. */
import { api } from '../api.js';
import { AGE_BINS, basemap, BASEMAPS, fitBbox, fly, getMap, pointsGeoJSON, RAIN_COLORS, RISK_COLORS, setBasemap, setData, setRain, setRisk, show } from '../map.js';
import { isReliable, loadObservations, visibleObservations } from '../data.js';
import { store } from '../store.js';
import { incidentInfo } from './incendio.js';
import { openModal, placeForm, reportForm } from '../ui.js';
import { $, ago, dual, keepPlace, fmtDateTime, fmtNum, fmtUTC, html, RISK, SENSOR_LABEL, toast, todayChile } from '../util.js';

const RANGES = [[6, 'Últimas 6 horas', '6 h'], [24, 'Hoy', '24 h'], [48, '2 días', '48 h'], [168, 'Semana', '7 días']];
const SOURCE_NAMES = {
  GOES19_FDCF: 'GOES-19 · cada 10 min', GOES16_FDCF: 'GOES-16', VIIRS_NOAA20_NRT: 'VIIRS NOAA-20', VIIRS_NOAA21_NRT: 'VIIRS NOAA-21',
  VIIRS_SNPP_NRT: 'VIIRS Suomi NPP', MODIS_NRT: 'MODIS Terra/Aqua',
};
let mounted = false;
let handlers = [];
let popup = null;
const layers = { risk: false, rain: false, reports: true, places: true };
// Los cinco niveles de anomalía de lluvia que calcula backend/rain.py (leyenda corta).
const RAIN_LEVELS = [['muy_seco', 'Mucho menos'], ['seco', 'Menos'], ['normal', 'Normal'], ['humedo', 'Más'], ['muy_humedo', 'Mucho más']];

function legend() {
  $('#map-legend').innerHTML = String(html`<div class="legend-title">¿Hace cuánto se vio el calor?</div>
    <div class="legend-row">${AGE_BINS.map((b) => html`<span class="legend-item"><span class="sw" style="background:${b.color}"></span>${b.label}</span>`)}</div>
    <div class="legend-row" style="margin-top:4px"><span class="legend-item"><span class="sw sw-sq" style="background:#ff7a2e;opacity:.6"></span>${dual('Zona de unos 2 km', 'Píxel GOES (~2–3 km)')}</span>
      <span class="legend-item"><span class="sw" style="background:#ff7a2e"></span>${dual('Punto más preciso', 'VIIRS/MODIS')}</span>
      <span class="legend-item"><span class="sw sw-ring"></span>${dual('Incendio que informa CONAF', 'Incendio CONAF (oficial)')}</span>
      ${layers.reports ? html`<span class="legend-item"><span class="sw" style="background:#6250d6"></span>Aviso de vecino revisado</span>` : ''}</div>
    ${layers.risk ? html`<div class="legend-row" style="margin-top:4px">${Object.entries(RISK).map(([k, r]) => html`<span class="legend-item"><span class="sw" style="background:${RISK_COLORS[k]}"></span>${r.label}</span>`)}</div>
      <div class="legend-note">${dual('Cada nivel tiene además su trama.', 'Cada nivel se distingue también por su trama, no solo por el color.')}</div>` : ''}
    ${layers.rain ? html`<div class="legend-row" style="margin-top:4px">${RAIN_LEVELS.map(([k, label]) => html`<span class="legend-item"><span class="sw" style="background:${RAIN_COLORS[k]}"></span>${label}</span>`)}</div>
      <div class="legend-note">Junio–hoy vs. normal 1991-2020. Es contexto del combustible, no cambia el peligro de hoy.${store.get('risk')?.rain_source?.name ? ` Fuente: ${store.get('risk').rain_source.name}.` : ''}</div>` : ''}
    <div class="legend-note">${dual('Calor no siempre es incendio. Los puntos pálidos son dudosos.', 'Un foco de calor no confirma un incendio. Los puntos tenues tienen confianza baja.')}</div>`);
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
    const id = e.features?.[0]?.properties?.id;
    const obs = (store.get('observations') || []).find((o) => o.id === id);
    if (obs) detailPopup(obs, e.lngLat);
  };
  const onReport = (e) => {
    const p = e.features[0].properties;
    popup?.remove();
    popup = new maplibregl.Popup({ maxWidth: '280px' }).setLngLat(e.lngLat).setHTML(String(html`<div class="tiny">Aviso de un vecino, revisado por BRASA</div>
      <b>${p.kind_label}</b> · <span class="muted">${ago(p.created_at)}</span><p class="small" style="margin-top:6px">${p.description || 'Sin descripción.'}</p>
      ${p.has_photo ? html`<img class="photo" alt="Foto del reporte" src="/api/reports/${p.id}/photo" />` : ''}
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
  const onOfficial = (e) => {
    const id = e.features?.[0]?.properties?.id;
    const fire = store.get('official')?.fires?.find((f) => f.id === id);
    if (fire) officialPopup(fire, e.lngLat);
  };
  for (const [layer, fn] of [['detections', onDetection], ['goes-pixels', onDetection], ['reports', onReport], ['risk-fill', onRisk], ['rain-fill', onRain], ['official', onOfficial]]) {
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

function sourcesHtml(status) {
  if (!status) return html`<p class="small muted">Sin información de las fuentes.</p>`;
  const runs = status.runs || [];
  if (!runs.length) return html`<p class="small muted">Aún no hay ingestas registradas. ${{ interna: 'La primera ocurre al iniciar el servidor.', cron: 'La ingesta corre cada 10 minutos: la primera llegará en unos minutos.' }[status.ingest_mode] || 'La ingesta automática está apagada (BRASA_SCHEDULER=0).'}</p>`;
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
  const official = (store.get('official')?.fires || []).filter((f) => f.status !== 'extinguido');
  container.innerHTML = String(html`
    <h1 class="view-title">Puntos de calor en Chile</h1>
    <p class="lede">${dual('Calor visto desde el espacio: puede ser un incendio, una quema o una industria. Toca un punto para saber más.', 'GOES-Este cada 10 min y VIIRS/MODIS en cada pasada. Toca un foco para ver su ficha.')}</p>
    <div id="goes-gap">${gapNote()}</div>
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
      <div class="switch-row"><div class="grow"><b class="small">Peligro de incendio hoy</b><div class="tiny muted">${dual('Pinta cada comuna según el clima de hoy.', 'Índice 30-30-30 diario por comuna (Open-Meteo).')}</div></div><label class="switch"><input type="checkbox" data-layer="risk" aria-label="Mostrar el peligro de incendio de hoy" ${layers.risk ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Lluvia de la temporada</b><div class="tiny muted">${dual('¿Dónde ha llovido menos que un año normal?', 'Junio–hoy vs. normal 1991-2020 (Open-Meteo)')}</div></div><label class="switch"><input type="checkbox" data-layer="rain" aria-label="Mostrar la lluvia de la temporada" ${layers.rain ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Avisos de vecinos</b><div class="tiny muted">Solo los revisados por un voluntario.</div></div><label class="switch"><input type="checkbox" data-layer="reports" aria-label="Mostrar avisos de vecinos" ${layers.reports ? 'checked' : ''} /><span></span></label></div>
      <div class="switch-row"><div class="grow"><b class="small">Mis lugares</b></div><label class="switch"><input type="checkbox" data-layer="places" aria-label="Mostrar mis lugares" ${layers.places ? 'checked' : ''} /><span></span></label></div>
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
  }));
  container.querySelector('#f-reliable').addEventListener('change', (e) => store.set('obsFilter', { ...store.get('obsFilter'), reliable: e.target.checked }));
  container.querySelectorAll('[data-sensor]').forEach((b) => b.addEventListener('click', () => {
    const current = store.get('obsFilter');
    store.set('obsFilter', { ...current, sensors: { ...current.sensors, [b.dataset.sensor]: current.sensors[b.dataset.sensor] === false } });
  }));
  container.querySelectorAll('[data-zone]').forEach((b) => b.addEventListener('click', () => { const z = zones[b.dataset.zone]; if (z) fitBbox(z.bbox); }));
  container.querySelectorAll('[data-basemap]').forEach((b) => b.addEventListener('click', () => { setBasemap(b.dataset.basemap); render(container, params); }));
  container.querySelectorAll('[data-layer]').forEach((input) => input.addEventListener('change', async () => {
    layers[input.dataset.layer] = input.checked;
    // Peligro y lluvia son excluyentes: dos coropletas sobre las mismas comunas se taparían
    // entre sí, y la lluvia (contexto del combustible) no debe leerse como el peligro de hoy.
    const other = { risk: 'rain', rain: 'risk' }[input.dataset.layer];
    if (input.checked && other) {
      layers[other] = false;
      const otherInput = container.querySelector(`[data-layer="${other}"]`);
      if (otherInput) otherInput.checked = false;
    }
    applyLayers();
    if (['risk', 'rain'].includes(input.dataset.layer) && input.checked) await loadRisk();
    legend();
  }));
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
  show('risk-fill', layers.risk);
  show('rain-fill', layers.rain);
  show('reports', layers.reports);
  show(['places', 'place-radius-fill', 'place-radius-line'], layers.places);
}

let unsubs = [];
export default {
  id: 'mapa',
  sheet: 'peek',
  async mount(container, { params }) {
    mounted = true;
    show(['detections', 'goes-pixels', 'goes-pixels-line'], true);
    show(['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event'], false);
    applyLayers();
    legend();
    $('#map-legend').classList.add('mobile-show');
    bindMap();
    loadReports();
    show('official', true);
    loadOfficial().then(() => mounted && keepPlace(container, () => render(container, {})));
    if (layers.risk || layers.rain) loadRisk();
    if (params?.lat && params?.lon) fly(Number(params.lon), Number(params.lat), Number(params.z) || 11);
    await render(container, params);
    // Datos nuevos: se redibuja el panel sin perder el lugar. El estado de las fuentes solo toca su bloque.
    unsubs = ['observations', 'obsFilter', 'basemapOffline'].map((k) => store.on(k, () => mounted && keepPlace(container, () => render(container, {}))));
    unsubs.push(store.on('status', () => {
      const el = mounted && container.querySelector('#sources-block');
      if (el) el.innerHTML = String(sourcesBlock());
      const gap = mounted && container.querySelector('#goes-gap');
      if (gap) gap.innerHTML = String(gapNote());
    }));
  },
  unmount() {
    mounted = false;
    unsubs.forEach((u) => u());
    popup?.remove();
    const map = getMap();
    handlers.forEach(([layer, fn]) => map.off('click', layer, fn));
    handlers = [];
    show(['explore', 'official'], false);
    $('#map-legend').classList.remove('mobile-show');
  },
};
