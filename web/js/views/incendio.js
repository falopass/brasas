/* Ficha de un incidente en vivo: la evidencia satelital agrupada, su estado en palabras sencillas,
 * la línea de tiempo (qué vio cada satélite y cuándo) y la reproducción hora a hora de la huella.
 * Usa el mismo motor que los casos históricos (backend/cases.py) y nunca se presenta como fuente oficial. */
import { api } from '../api.js';
import { timeChart } from '../charts.js';
import { fitBbox, setData, show } from '../map.js';
import { placeForm, reportForm } from '../ui.js';
import { $, ago, dual, emberSvg, fmtDateTime, fmtNum, fmtUTC, html, minutesSince, parseUTC, pixelSquare, SENSOR_LABEL } from '../util.js';

const EMPTY = { type: 'FeatureCollection', features: [] };
const LAYERS = ['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes'];
const REFRESH_MS = 3 * 60 * 1000;

/** Cada estado: tono visual, título y explicación para cualquier persona; la definición exacta, para la lectura detallada. */
export const INCIDENT = {
  anomalia: { tone: 'aviso', title: 'Una señal de calor', text: 'Un satélite vio calor una vez. Puede ser un incendio, una quema o una industria: aún no hay más pruebas.', tech: 'Anomalía: una sola detección confiable o solo detecciones de confianza baja.' },
  posible: { tone: 'riesgo', title: 'Posible incendio', text: 'Los satélites vieron calor en el mismo lugar más de una vez, o dos satélites distintos lo vieron. Es probable que sea fuego.', tech: 'Posible: ≥ 2 detecciones confiables en momentos distintos, o 2 sensores distintos (p. ej. GOES + VIIRS).' },
  reportado: { tone: 'urgente', title: 'Posible incendio, también visto por vecinos', text: 'Además del satélite, un vecino avisó de fuego o humo cerca y BRASA revisó su aviso.', tech: 'Reportado: evidencia satelital + reporte ciudadano verificado por moderación a ≤ 3 km.' },
  confirmado: { tone: 'urgente', title: 'Incendio reconocido por la autoridad', text: 'Una fuente oficial informa este incendio. Sigue sus instrucciones.', tech: 'Confirmado: con referencia oficial (CONAF/SENAPRED). BRASA no confirma por su cuenta.' },
  controlado: { tone: 'aviso', title: 'Controlado según la autoridad', text: 'La autoridad lo informa como controlado. Aún puede haber humo o rebrotes.', tech: 'Controlado: según fuente oficial.' },
  extinguido: { tone: 'tranquilo', title: 'Sin calor nuevo', text: 'Los satélites no ven calor aquí hace más de un día. No significa «apagado oficialmente».', tech: 'Extinguido (según satélite): 24 h sin detecciones nuevas.' },
};
const FIXED = { tone: 'tranquilo', title: 'Calor de una fuente fija', text: 'Este calor aparece siempre en el mismo lugar (un volcán o una industria). Por eso BRASA no avisa por él.', tech: 'Fuente fija probable: toda la evidencia cae en un volcán activo o en una celda con calor ≥ 8 días de los últimos 30.' };

export const incidentInfo = (inc) => (inc.fixed_source ? FIXED : INCIDENT[inc.status] || INCIDENT.anomalia);

let mounted = false;
let S = null;
let timer = null;
let seq = 0;

const sensorWord = (s) => (s === 'ABI' ? 'el satélite que mira cada 10 min' : 'un satélite de paso');
const confWord = (c) => ({ alta: 'alta', nominal: 'normal', media: 'media', baja: 'baja' }[c] || 'sin dato');

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

function render(container, data) {
  const inc = data.incident;
  const info = incidentInfo(inc);
  const tl = data.timeline;
  const stale = data.data_as_of && minutesSince(data.data_as_of) > 30;
  const where = inc.comuna ? `${inc.comuna}, ${inc.region}` : 'Fuera del territorio chileno';
  const recent = [...data.evidence].reverse().slice(0, 40);
  const latency = Object.entries(data.latency);
  container.innerHTML = String(html`
    <a class="btn btn-sm btn-ghost" href="#/mapa">← Mapa</a>
    <div class="ember-hero st-${info.tone}" role="status" style="margin-top:10px">${emberSvg({ tone: info.tone })}
      <div><div class="hero-label">${info.title}</div>
        <small>${where}. ${dual(info.text, info.tech)}</small>
        ${['reportado', 'confirmado'].includes(inc.status) ? html`<div class="btn-row hero-cta"><a class="btn btn-sm btn-call" href="tel:132">Llamar a Bomberos · 132</a></div>` : ''}</div></div>
    ${stale ? html`<div class="callout callout-warn stale-note" role="alert"><b>Los datos de los satélites no se actualizan desde ${ago(data.data_as_of)}.</b> Que no veamos calor nuevo no significa que no lo haya.</div>` : ''}
    <div class="kpis">
      <div class="kpi"><small>${dual('veces que se vio calor', 'detecciones')}</small><strong>${fmtNum(inc.n_obs)}</strong></div>
      <div class="kpi"><small>${dual('primera vez', 'primera detección')}</small><strong class="small-figure">${ago(inc.first_seen_at)}</strong></div>
      <div class="kpi"><small>${dual('última vez', 'última detección')}</small><strong class="small-figure">${ago(inc.last_seen_at)}</strong></div>
    </div>
    <p class="small">${dual(`Lo vieron ${inc.sensors.length >= 2 ? 'dos tipos de satélite distintos' : sensorWord(inc.sensors[0])}. ${inc.n_reliable < inc.n_obs ? `${inc.n_obs - inc.n_reliable} de las señales son dudosas.` : ''}`,
      `Sensores: ${inc.sensors.map((s) => SENSOR_LABEL[s] || s).join(' + ')} · confiables ${inc.n_reliable}/${inc.n_obs} · FRP máx. ${inc.max_frp != null ? `${fmtNum(inc.max_frp, 1)} MW` : 'n/d'} · estado desde ${fmtDateTime(inc.status_changed_at)}.`)}</p>
    <div class="btn-row"><button class="btn btn-primary" id="in-watch">Avisarme si crece</button><button class="btn btn-ghost" id="in-report">Contar lo que veo</button></div>
    ${tl ? html`<h2 class="section">${dual('Cómo ha ido cambiando', 'Reproducción hora a hora')}</h2>
      <div class="player" role="group" aria-label="Reproducción del incidente">
        <div class="player-time"><strong id="in-time"></strong><span class="tiny muted">${dual('zona con calor:', 'huella:')} <b id="in-area">—</b></span></div>
        <div class="player-controls"><input type="range" id="in-slider" min="0" max="${tl.hours.length - 1}" step="1" value="${tl.hours.length - 1}" aria-label="Hora" /></div>
      </div>
      <div id="in-chart"></div>
      <p class="tiny muted">${dual('La zona marcada en el mapa es todo lo que los satélites vieron caliente: es aproximada y no es el borde oficial del fuego.', tl.footprint_note)}</p>` : ''}
    <h2 class="section">${dual('Qué vio cada satélite', 'Evidencia')} <span class="tag">${fmtNum(data.evidence_total)}</span></h2>
    <ul class="list evidence-list">${recent.map((e) => html`<li>
      <span class="grow"><span class="event-time">${fmtDateTime(e.observed_at)}</span>
        <span class="small">${dual(`Calor visto por ${sensorWord(e.sensor)} · señal ${confWord(e.confidence)}`,
          `${SENSOR_LABEL[e.sensor] || e.sensor} ${e.satellite || ''} · conf. ${e.confidence || 'n/d'} · FRP ${e.frp_mw != null ? fmtNum(e.frp_mw, 1) : 'n/d'} MW · ${fmtUTC(e.observed_at)} · llegó a BRASA ${e.delay_min} min después`)}</span></span></li>`)}</ul>
    ${data.evidence_total > recent.length ? html`<p class="tiny muted">Se muestran las ${recent.length} más recientes.</p>` : ''}
    ${latency.length ? html`<div class="callout x-tech" style="margin-top:12px"><b>Latencia (observación → BRASA).</b> ${latency.map(([s, l]) => `${SENSOR_LABEL[s] || s}: mediana ${l.p50_min} min, máx. ${l.max_min} min (${l.n})`).join(' · ')}. Incluye el tiempo de publicación de NASA/NOAA y el ciclo de 10 min de BRASA.</div>` : ''}
    <div class="callout" style="margin-top:12px"><b>${dual('BRASA no es una fuente oficial.', 'Fuente no oficial.')}</b> ${data.official} Emergencias: 132 Bomberos · 130 CONAF.</div>
    <p class="tiny muted x-tech">Incidente ${inc.id} · ${inc.lat.toFixed(4)}, ${inc.lon.toFixed(4)}</p>`);

  container.querySelector('#in-watch').addEventListener('click', () => placeForm(null, { lat: inc.lat, lon: inc.lon, name: inc.comuna ? `Cerca de ${inc.comuna}` : '' }));
  container.querySelector('#in-report').addEventListener('click', () => reportForm({ lat: inc.lat, lon: inc.lon }));
  S.chart?.destroy();
  S.chart = null;
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
  let data;
  try { data = await api.incident(id); } catch (err) {
    if (!mounted || mine !== seq) return;
    if (first) container.innerHTML = String(html`<a class="btn btn-sm btn-ghost" href="#/mapa">← Mapa</a>
      <h1 class="view-title" style="margin-top:12px">No encontramos este incidente</h1><p class="muted">${err.message}</p>`);
    return;
  }
  if (!mounted || mine !== seq) return;
  const keep = S && S.id === id && S.tl && data.timeline && S.index < S.tl.hours.length - 1 ? S.index : null;
  S = { ...(S?.id === id ? S : {}), id, container, evidence: data.evidence, tl: data.timeline, index: keep ?? (data.timeline ? data.timeline.hours.length - 1 : 0) };
  if (first && data.timeline) fitBbox(data.timeline.bbox, 30);
  render(container, data);
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
    for (const id of ['case-goes', 'case-points', 'case-footprint']) setData(id, EMPTY);
    show(LAYERS, false);
    $('#map-legend').innerHTML = '';
  },
};
