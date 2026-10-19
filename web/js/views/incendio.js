/* Ficha de un incidente en vivo: la evidencia satelital agrupada, su estado en palabras sencillas,
 * la línea de tiempo (qué vio cada satélite y cuándo) y la reproducción hora a hora de la huella.
 * Usa el mismo motor que los casos históricos (backend/cases.py) y nunca se presenta como fuente oficial. */
import { api } from '../api.js';
import { timeChart } from '../charts.js';
import { fitBbox, setData, show } from '../map.js';
import { placeForm, reportForm } from '../ui.js';
import { $, ago, download, dual, emberSvg, escapeHtml, fmtDateTime, fmtNum, fmtUTC, html, keepPlace, minutesSince, parseUTC, pixelSquare, SENSOR_LABEL, toast } from '../util.js';

const EMPTY = { type: 'FeatureCollection', features: [] };
const LAYERS = ['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes'];
const REFRESH_MS = 3 * 60 * 1000;

/** Cada estado: tono visual, título y explicación para cualquier persona; la definición exacta, para la lectura detallada. */
export const INCIDENT = {
  anomalia: { tone: 'aviso', short: 'Señal de calor', title: 'Una señal de calor', text: 'Un satélite vio calor una vez. Puede ser un incendio, una quema o una industria: aún no hay más pruebas.', tech: 'Anomalía: una sola detección confiable o solo detecciones de confianza baja.' },
  posible: { tone: 'riesgo', short: 'Posible incendio', title: 'Posible incendio', text: 'Los satélites vieron calor en el mismo lugar más de una vez, o dos satélites distintos lo vieron. Es probable que sea fuego.', tech: 'Posible: ≥ 2 detecciones confiables en momentos distintos, o 2 sensores distintos (p. ej. GOES + VIIRS).' },
  reportado: { tone: 'urgente', short: 'Visto por vecinos', title: 'Posible incendio, también visto por vecinos', text: 'Además del satélite, un vecino avisó de fuego o humo cerca y BRASA revisó su aviso.', tech: 'Reportado: evidencia satelital + reporte ciudadano verificado por moderación a ≤ 3 km.' },
  confirmado: { tone: 'urgente', short: 'Confirmado por CONAF', title: 'Incendio informado por CONAF', text: 'CONAF informa este incendio. Sigue las instrucciones de SENAPRED y de la autoridad local.', tech: 'Confirmado: unido a un incendio del reporte público de CONAF a ≤ 3 km. BRASA no confirma por su cuenta.' },
  controlado: { tone: 'aviso', short: 'Controlado', title: 'Controlado según CONAF', text: 'CONAF lo informa como controlado. Aún puede haber humo o rebrotes.', tech: 'Controlado: según el reporte público de CONAF.' },
  extinguido: { tone: 'tranquilo', short: 'Sin calor nuevo', title: 'Sin calor nuevo', text: 'Los satélites no ven calor aquí hace más de un día. No significa «apagado oficialmente», salvo que CONAF lo informe.', tech: 'Extinguido: 24 h sin detecciones nuevas, o extinguido según CONAF si está unido a su reporte.' },
};
const FIXED = { tone: 'tranquilo', short: 'Fuente fija', title: 'Calor de una fuente fija', text: 'Este calor aparece siempre en el mismo lugar (un volcán o una industria). Por eso BRASA no avisa por él.', tech: 'Fuente fija probable: toda la evidencia cae en un volcán activo o en una celda con calor ≥ 8 días de los últimos 30.' };

export const incidentInfo = (inc) => (inc.fixed_source ? FIXED : INCIDENT[inc.status] || INCIDENT.anomalia);

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

const AVISO = 'BRASA no es fuente oficial: un incidente agrupa detecciones satelitales y puede ser un incendio, una quema o una industria. Sigue a SENAPRED y CONAF.';

/** La geometría de la última huella del timeline, si existe. */
const lastFootprint = (data) => data.timeline?.frames?.at(-1)?.geometry || null;

/** Los mismos datos de la ficha como GeoJSON, para brigadistas y análisis técnico. */
function incidentGeoJSON(data) {
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
function incidentKML(data) {
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
    <p class="small">${dual(`Lo vieron ${inc.sensors.length >= 2 ? 'dos tipos de satélite distintos' : sensorWord(inc.sensors[0])}. ${inc.n_reliable < inc.n_obs ? `${inc.n_obs - inc.n_reliable} de las señales son dudosas.` : ''}`,
      `Sensores: ${inc.sensors.map((s) => SENSOR_LABEL[s] || s).join(' + ')} · confiables ${inc.n_reliable}/${inc.n_obs} · FRP máx. ${inc.max_frp != null ? `${fmtNum(inc.max_frp, 1)} MW` : 'n/d'} · estado desde ${fmtDateTime(inc.status_changed_at)}.`)}</p>
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
      <p class="tiny muted">${dual('La zona marcada en el mapa es todo lo que los satélites vieron caliente: es aproximada y no es el borde oficial del fuego.', tl.footprint_note)}</p>` : ''}
    <h2 class="section">${dual('Qué vio cada satélite', 'Evidencia')} <span class="tag">${fmtNum(data.evidence_total)}</span></h2>
    <ul class="list evidence-list">${recent.map((e) => html`<li>
      <span class="grow"><span class="event-time">${fmtDateTime(e.observed_at)}</span>
        <span class="small">${dual(`Calor visto por ${sensorWord(e.sensor)} · señal ${confWord(e.confidence)}`,
          `${SENSOR_LABEL[e.sensor] || e.sensor} ${e.satellite || ''} · conf. ${e.confidence || 'n/d'} · FRP ${e.frp_mw != null ? fmtNum(e.frp_mw, 1) : 'n/d'} MW · ${fmtUTC(e.observed_at)} · llegó a BRASA ${e.delay_min} min después`)}</span></span></li>`)}</ul>
    ${data.evidence_total > recent.length ? html`<p class="tiny muted">Se muestran las ${recent.length} más recientes.</p>` : ''}
    <div id="in-testigos"></div>
    ${latency.length ? html`<div class="callout x-tech" style="margin-top:12px"><b>Latencia (observación → BRASA).</b> ${latency.map(([s, l]) => `${SENSOR_LABEL[s] || s}: mediana ${l.p50_min} min, máx. ${l.max_min} min (${l.n})`).join(' · ')}. Incluye el tiempo de publicación de NASA/NOAA y el ciclo de 10 min de BRASA.</div>` : ''}
    <div class="callout" style="margin-top:12px"><b>${dual('BRASA no es una fuente oficial.', 'Fuente no oficial.')}</b> ${data.official} Emergencias: 132 Bomberos · 130 CONAF.</div>
    <p class="tiny muted x-tech">Incidente ${inc.id} · ${inc.lat.toFixed(4)}, ${inc.lon.toFixed(4)}</p>`);

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
  loadTestigos(container, inc);
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

/** «Vecinos que ya lo vieron»: reportes ciudadanos verificados cerca del incidente.
 * Si la petición falla, la sección se retira y el resto de la ficha sigue igual. */
async function loadTestigos(container, inc) {
  const host = container.querySelector('#in-testigos');
  if (!host) return;
  let data;
  try { data = await api.incidentReports(inc.id); } catch { host.remove(); return; }
  if (!host.isConnected) return;
  const rows = (data.reports || []).slice(0, 5);
  host.innerHTML = String(html`
    <h2 class="section">${dual('Vecinos que ya lo vieron', 'Reportes ciudadanos verificados a ≤ 3 km')}</h2>
    ${rows.length ? html`<ul class="list">${rows.map((r) => html`<li>
      <span class="grow"><span class="event-time">${r.kind_label}</span>
        <span class="small">${dual(`${ago(r.created_at)} · a ${fmtNum(r.distance_km, 1)} km`,
          `${r.kind_label} · ${ago(r.created_at)} (${fmtUTC(r.created_at)}) · ${fmtNum(r.distance_km, 1)} km del centro${r.comuna ? ` · ${r.comuna}` : ''}`)}</span></span></li>`)}</ul>
      ${data.reports.length > 5 ? html`<p class="tiny muted">Se muestran los 5 más recientes.</p>` : ''}` : html`
      <p class="small muted">Nadie ha reportado humo o fuego aquí todavía.</p>
      <div class="btn-row"><button class="btn btn-ghost" id="in-testigos-report">Contar lo que veo</button></div>`}`);
  host.querySelector('#in-testigos-report')?.addEventListener('click', () => reportForm({ lat: inc.lat, lon: inc.lon }));
}

async function load(container, id, first) {
  const mine = ++seq;
  let data;
  try { data = await api.incident(id); } catch (err) {
    if (!mounted || mine !== seq) return;
    if (first) container.innerHTML = String(html`<a class="btn btn-sm btn-ghost" id="in-back" href="#/mapa">← Mapa</a>
      <h1 class="view-title" style="margin-top:12px">No encontramos este incidente</h1><p class="muted">${err.message}</p>`);
    return;
  }
  if (!mounted || mine !== seq) return;
  const keep = S && S.id === id && S.tl && data.timeline && S.index < S.tl.hours.length - 1 ? S.index : null;
  S = { ...(S?.id === id ? S : {}), id, container, evidence: data.evidence, tl: data.timeline, index: keep ?? (data.timeline ? data.timeline.hours.length - 1 : 0) };
  if (first && data.timeline) fitBbox(data.timeline.bbox, 30);
  keepPlace(container, () => render(container, data));
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
