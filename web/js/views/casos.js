/* Casos históricos: reconstrucción hora a hora con detecciones reales, huella acumulada, clima ERA5 y eventos.
 * Un solo reloj (índice horario) sincroniza el mapa 2D, la vista 3D, los gráficos y la lista de eventos. */
import { api } from '../api.js';
import { timeChart } from '../charts.js';
import { fitBbox, fly, setData, show } from '../map.js';
import { store } from '../store.js';
import { $, dual, fmtDay, fmtNum, html, pixelSquare, TZ, toast } from '../util.js';

const EMPTY = { type: 'FeatureCollection', features: [] };
const SPEEDS = [[1, 'Lento', '1 h/s'], [3, 'Normal', '3 h/s'], [8, 'Rápido', '8 h/s']];
const TRAIL_HOURS = 6;

let mounted = false;
let S = null; // estado del caso abierto

/** Cada momento clave en palabras sencillas; la etiqueta técnica del servidor queda para la lectura detallada. */
function plainEvent(e) {
  const num = e.label.match(/[\d.]+(?=\s*(km|ha|MW)|$)/)?.[0];
  return {
    inicio: 'Los satélites ven el fuego por primera vez',
    secundario: `Aparece calor${num ? ` a ${num} km` : ''} del fuego: pudo saltar, por ejemplo con brasas que lleva el viento`,
    crecimiento: `La hora en que más creció${num ? ` (+${num} ha)` : ''}`,
    frp: 'El momento en que el fuego tuvo más fuerza',
    actividad: `La hora con más puntos de calor${num ? ` (${num})` : ''}`,
  }[e.kind] || e.label;
}

function chileTime(date) {
  return date.toLocaleString('es-CL', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
}
const shortTime = (date) => date.toLocaleString('es-CL', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
const utcDate = (s) => new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`);

// ------------------------------------------------------------------ catálogo
async function renderCatalog(container) {
  let data;
  try { data = await api.cases(); } catch (err) { container.innerHTML = String(html`<p class="muted">${err.message}</p>`); return; }
  show(['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event'], false);
  fitBbox([-74.5, -39.5, -70, -32], 40);
  $('#map-legend').innerHTML = '';
  container.innerHTML = String(html`
    <h1 class="view-title">Grandes incendios, hora a hora</h1>
    <p class="lede">${dual('Mira cómo avanzaron tres incendios que marcaron a Chile: lo que vieron los satélites, el viento y el calor de esas horas. Todo con datos reales.', 'Reconstrucción con detecciones satelitales reales, huella acumulada, clima ERA5 y eventos derivados. Sin datos inventados.')}</p>
    ${data.cases.map((c) => html`<article class="card clickable case-card" data-case="${c.id}" tabindex="0" role="link" aria-label="Abrir ${c.title}">
      <span class="case-year" aria-hidden="true">${c.start_utc.slice(0, 4)}</span>
      <div class="card-title">${c.title}</div><div class="card-sub">${c.subtitle}</div>
      <div class="tiny muted" style="margin-top:4px">${fmtDay(c.start_utc.slice(0, 10))} → ${fmtDay(c.end_utc.slice(0, 10))}</div>
      <div class="badges">${c.goes ? html`<span class="tag tag-live">${dual(`Imágenes cada ${c.goes.cadence_min} min`, `GOES-16 · cada ${c.goes.cadence_min} min`)}</span>` : html`<span class="tag">${dual('Pocas imágenes', 'Sin GOES')}</span>`}
        <span class="tag x-tech">VIIRS/MODIS (FIRMS)</span><span class="tag">${dual('Clima de esas horas', 'Clima ERA5')}</span></div>
    </article>`)}
    <div class="callout" style="margin-top:14px"><b>Cómo leerlo.</b> ${dual('Los satélites ven calor, no el borde exacto del fuego, y el humo espeso a veces lo tapa. Por eso la zona marcada es aproximada: suele verse más grande que lo que realmente se quemó.', 'Los satélites registran píxeles calientes en cada pasada; no ven el perímetro ni el fuego bajo humo denso. La huella acumulada sobreestima la superficie, sobre todo con GOES (2–3 km). Para la superficie oficial, importa el perímetro de CONAF.')}</div>
    <p class="tiny muted x-tech" style="margin-top:10px">${data.note}</p>`);
  container.querySelectorAll('[data-case]').forEach((card) => {
    const go = () => { location.hash = `#/casos/${card.dataset.case}`; };
    card.addEventListener('click', go);
    card.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  });
}

// ------------------------------------------------------------------ caso abierto
function goesObservations(goes) {
  if (!goes) return [];
  const start = utcDate(goes.start_utc).getTime();
  return goes.rows.map(([minute, lat, lon, frp, bright, conf]) => ({ t: start + minute * 60000, lat, lon, frp, conf, sensor: 'ABI' }));
}

function polarObservations(points) {
  return points.filter((p) => ['alta', 'nominal'].includes(p.confidence) || p.confidence === null)
    .map((p) => ({ t: utcDate(p.observed_at).getTime(), lat: p.lat, lon: p.lon, frp: p.frp_mw, sensor: p.sensor }));
}

function frameAt(index) {
  const end = S.hourTimes[index] + 3600000;
  let frame = null;
  for (const f of S.timeline.frames) { if (utcDate(f.t).getTime() <= end) frame = f; else break; }
  return frame;
}

function paint(index) {
  const end = S.hourTimes[index] + 3600000;
  const from = end - TRAIL_HOURS * 3600000;
  const goesFeatures = []; const dotFeatures = []; const globeDots = [];
  for (const o of S.goes) {
    if (o.t < from) continue;
    if (o.t >= end) break;
    if (o.conf < 1) continue;
    const age = (end - o.t) / 3600000;
    goesFeatures.push({ type: 'Feature', geometry: pixelSquare(o.lon, o.lat, 2.5), properties: { age_h: age } });
    globeDots.push({ lon: o.lon, lat: o.lat, age_h: age });
  }
  for (const o of S.polar) {
    if (o.t < end - 24 * 3600000 || o.t >= end) continue;
    const age = (end - o.t) / 3600000;
    dotFeatures.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [o.lon, o.lat] }, properties: { age_h: age } });
    globeDots.push({ lon: o.lon, lat: o.lat, age_h: age });
  }
  const frame = S.showFootprint ? frameAt(index) : null;
  setData('case-goes', { type: 'FeatureCollection', features: goesFeatures });
  setData('case-points', { type: 'FeatureCollection', features: dotFeatures });
  setData('case-footprint', frame ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: frame.geometry, properties: {} }] } : EMPTY);
  if (S.globe) S.globe.updateGlobe(frame?.geometry || null, globeDots);
}

function updateReadout(index) {
  const h = S.timeline.hours[index];
  const date = new Date(S.hourTimes[index]);
  const root = S.container;
  root.querySelector('#pl-time').textContent = chileTime(date);
  root.querySelector('#pl-utc').textContent = `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
  const slider = root.querySelector('#pl-slider');
  slider.value = String(index);
  slider.style.setProperty('--p', `${(100 * index) / Math.max(1, S.hourTimes.length - 1)}%`);
  root.querySelector('#k-pixels').textContent = fmtNum(h.n_good);
  root.querySelector('#k-cover').textContent = h.footprint_ha ? `${fmtNum(h.footprint_ha)} ha` : '—';
  root.querySelector('#k-frp').textContent = h.frp_max ? `${fmtNum(h.frp_max)} MW` : '—';
  const w = S.weather;
  const wi = w ? S.weatherIndex[index] : -1;
  root.querySelector('#k-wind').textContent = wi >= 0 && Number.isFinite(w.wind_speed_10m[wi]) ? `${fmtNum(w.wind_speed_10m[wi])} km/h` : '—';
  root.querySelector('#k-temp').textContent = wi >= 0 && Number.isFinite(w.temperature_2m[wi]) ? `${fmtNum(w.temperature_2m[wi], 1)} °C` : '—';
  root.querySelector('#k-rh').textContent = wi >= 0 && Number.isFinite(w.relative_humidity_2m[wi]) ? `${fmtNum(w.relative_humidity_2m[wi])} %` : '—';
  const nowT = S.hourTimes[index] + 3600000;
  let currentEvent = -1;
  S.timeline.events.forEach((e, i) => { if (utcDate(e.t).getTime() <= nowT) currentEvent = i; });
  root.querySelectorAll('.event-list li').forEach((li, i) => li.setAttribute('aria-current', String(i === currentEvent)));
}

function seek(index) {
  S.index = Math.max(0, Math.min(S.hourTimes.length - 1, index));
  paint(S.index);
  updateReadout(S.index);
  S.chart?.setCursor(S.index);
}

function togglePlay(force) {
  const playing = force ?? !S.timer;
  clearInterval(S.timer); S.timer = null;
  S.container.querySelector('#pl-play').classList.toggle('playing', playing);
  S.container.querySelector('#pl-play').setAttribute('aria-label', playing ? 'Pausar' : 'Reproducir');
  if (!playing) return;
  if (S.index >= S.hourTimes.length - 1) seek(0);
  S.timer = setInterval(() => {
    if (S.index >= S.hourTimes.length - 1) return togglePlay(false);
    seek(S.index + 1);
  }, 1000 / S.speed);
}

function buildChart() {
  const host = S.container.querySelector('#case-chart');
  S.chart?.destroy();
  const hours = S.timeline.hours;
  const panels = [
    { id: 'n', title: 'Puntos de calor por hora', kind: 'bars', height: 84,
      series: [{ key: 'goes', label: 'GOES', color: 'var(--series-2)', values: hours.map((h) => h.n_goes) },
        { key: 'polar', label: 'VIIRS/MODIS', color: 'var(--series-1)', values: hours.map((h) => h.n_polar) }] },
    { id: 'cov', title: 'Zona con calor, acumulada', unit: 'ha', kind: 'line', area: true, series: [{ key: 'cov', label: 'Huella acumulada', color: 'var(--series-2)', values: hours.map((h) => h.footprint_ha || null) }] },
  ];
  if (S.weather) {
    const pick = (key) => S.weatherIndex.map((wi) => (wi >= 0 ? S.weather[key][wi] : null));
    panels.push(
      { id: 'w', title: 'Viento', unit: 'km/h', kind: 'line', series: [{ key: 'w', label: 'Viento', color: 'var(--series-1)', values: pick('wind_speed_10m') }], threshold: { value: 30, label: '30 km/h', direction: 'above' } },
      { id: 't', title: 'Calor', unit: '°C', kind: 'line', digits: 1, series: [{ key: 't', label: 'Temperatura', color: 'var(--series-2)', values: pick('temperature_2m') }], threshold: { value: 30, label: '30 °C', direction: 'above' } },
      { id: 'rh', title: 'Humedad del aire', unit: '%', kind: 'line', yMax: 100, series: [{ key: 'rh', label: 'Humedad', color: 'var(--series-1)', values: pick('relative_humidity_2m') }], threshold: { value: 30, label: '30 %', direction: 'below' } },
    );
  }
  S.chart = timeChart(host, { times: hours.map((h) => h.t), panels, cursor: S.index, onSeek: (i) => { togglePlay(false); seek(i); } });
}

async function loadWeather() {
  const mine = S;
  try {
    const w = await api.caseWeather(S.case.id);
    if (S !== mine) return; // el usuario abrió otro caso mientras llegaba la respuesta
    const index = new Map(w.hourly.time.map((t, i) => [utcDate(t).getTime(), i]));
    S.weather = w.hourly;
    S.weatherIndex = S.hourTimes.map((t) => index.get(t) ?? -1);
    S.container.querySelector('#weather-note').textContent = `${w.source}. ${w.note}`;
  } catch (err) {
    if (S !== mine) return;
    S.weather = null;
    S.container.querySelector('#weather-note').innerHTML = String(dual('El clima de esas horas no está disponible ahora. Vuelve a intentarlo más tarde.', `Clima ERA5 no disponible ahora (${err.message}). Se cargará cuando el servidor tenga conexión con Open-Meteo.`));
  }
  buildChart();
  updateReadout(S.index);
}

async function loadPolar(force) {
  const mine = S;
  const id = S.case.id;
  try {
    if (force) {
      const res = await api.loadCasePolar(id);
      if (S === mine) toast(`${fmtNum(res.count)} detecciones VIIRS/MODIS agregadas.`);
    }
    const { points } = await api.casePolar(id);
    if (S !== mine) return;
    S.polar = polarObservations(points).sort((a, b) => a.t - b.t);
    if (force) {
      const detail = await api.caseDetail(id);
      if (S !== mine) return;
      S.timeline = detail.timeline;
      renderCase(S.container, true);
    }
  } catch (err) { if (force && S === mine) toast(err.message, 'error'); }
}

function importPerimeter(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (!['FeatureCollection', 'Feature', 'Polygon', 'MultiPolygon'].includes(data.type)) throw new Error('El archivo no es GeoJSON.');
      const sample = JSON.stringify(data).match(/-?\d+\.\d+/g)?.slice(0, 2).map(Number) || [];
      if (sample.some((v) => Math.abs(v) > 180)) throw new Error('Las coordenadas no están en grados (WGS84). Conviértelo con scripts/convert_conaf.py.');
      setData('case-final', data);
      show('case-final', true);
      toast(`Perímetro importado: ${file.name}. Se muestra como estado final, no como avance en el tiempo.`);
    } catch (err) { toast(`No se pudo importar: ${err.message}`, 'error'); }
  };
  reader.readAsText(file);
}

function setViewButtons(is3d) {
  document.querySelector('.map-wrap').classList.toggle('globe-on', is3d);
  S.container.querySelector('#v3d').setAttribute('aria-pressed', String(is3d));
  S.container.querySelector('#v2d').setAttribute('aria-pressed', String(!is3d));
}

function show2D() {
  $('#globe').hidden = true;
  setViewButtons(false);
}

async function toggle3D() {
  const globeEl = $('#globe');
  if (!globeEl.hidden) return show2D();
  try {
    S.container.querySelector('#v3d').textContent = 'Cargando 3D…';
    const mod = await import('../globe.js');
    globeEl.hidden = false;
    const mine = S;
    const info = await mod.openGlobe(globeEl, { ionToken: store.get('config')?.ion_public_token, camera: S.case.camera });
    if (S !== mine || !S) { globeEl.hidden = true; return; }
    S.globe = mod;
    paint(S.index);
    if (!info.terrain) toast('Vista 3D sin relieve real: agrega CESIUM_ION_PUBLIC_TOKEN en el servidor para ver montañas.');
  } catch (err) {
    globeEl.hidden = true;
    toast(err.message, 'error');
  } finally {
    if (S) {
      S.container.querySelector('#v3d').textContent = '3D';
      setViewButtons(!globeEl.hidden);
    }
  }
}

function legend() {
  $('#map-legend').innerHTML = String(html`<div class="legend-title">${dual('Calor visto en las últimas 6 horas', `Reconstrucción · últimas ${TRAIL_HOURS} h`)}</div>
    <div class="legend-row"><span class="legend-item"><span class="sw sw-sq" style="background:#ff4b1f"></span>${dual('Hace menos de 1 h', '< 1 h')}</span>
      <span class="legend-item"><span class="sw sw-sq" style="background:#ff7a2e"></span>1 a 3 h</span>
      <span class="legend-item"><span class="sw sw-sq" style="background:#ffa54a"></span>3 a 6 h</span>
      <span class="legend-item"><span class="sw sw-sq" style="background:#d9471f;opacity:.45"></span>${dual('Zona con calor hasta esa hora', 'Huella acumulada')}</span>
      <span class="legend-item x-tech"><span class="sw sw-line"></span>Perímetro importado</span></div>
    <div class="legend-note">${dual('Es lo que vieron los satélites, no el borde oficial del incendio.', 'Huella = píxeles calientes observados, no perímetro oficial.')}</div>`);
}

function renderCase(container, keepIndex = false) {
  const c = S.case;
  const tl = S.timeline;
  const firms = store.get('config')?.firms_configured;
  container.innerHTML = String(html`
    <a class="btn btn-sm btn-ghost" href="#/casos">← Historia</a>
    <h1 class="view-title">${c.title}</h1>
    <p class="lede">${c.subtitle} · ${fmtDay(c.start_utc.slice(0, 10))} → ${fmtDay(c.end_utc.slice(0, 10))}</p>
    <div class="player" role="group" aria-label="Reproductor de la reconstrucción">
      <div class="player-time"><strong id="pl-time"></strong><span class="tiny muted x-tech" id="pl-utc"></span></div>
      <div class="player-controls">
        <button class="play-btn" id="pl-play" aria-label="Reproducir"></button>
        <input type="range" id="pl-slider" min="0" max="${S.hourTimes.length - 1}" step="1" value="0" aria-label="Hora de la reconstrucción" />
        <button class="btn btn-sm" id="pl-prev" aria-label="Momento clave anterior">‹ Antes</button><button class="btn btn-sm" id="pl-next" aria-label="Momento clave siguiente">Después ›</button>
      </div>
      <div class="player-controls" style="justify-content:space-between">
        <div class="segmented" role="group" aria-label="Velocidad">${SPEEDS.map(([v, l, t]) => html`<button data-speed="${v}" aria-pressed="${v === S.speed}">${dual(l, t)}</button>`)}</div>
        <div class="segmented" role="group" aria-label="Vista"><button id="v2d" aria-pressed="true">2D</button><button id="v3d" aria-pressed="false">3D</button></div>
      </div>
    </div>
    <div class="kpis">
      <div class="kpi"><small>${dual('puntos de calor en esa hora', 'píxeles en la hora')}</small><strong id="k-pixels">—</strong></div>
      <div class="kpi"><small>${dual('zona con calor (aprox.)', 'huella acumulada')}</small><strong id="k-cover">—</strong></div>
      <div class="kpi"><small>${dual('fuerza del fuego', 'FRP máx. hora')}</small><strong id="k-frp">—</strong></div>
      <div class="kpi"><small>viento</small><strong id="k-wind">—</strong></div>
      <div class="kpi"><small>${dual('calor', 'temperatura')}</small><strong id="k-temp">—</strong></div>
      <div class="kpi"><small>${dual('humedad del aire', 'HR')}</small><strong id="k-rh">—</strong></div>
    </div>
    <h2 class="section">Cómo fue avanzando</h2>
    <div class="chart-legend"><span class="legend-item"><span class="sw sw-sq" style="background:var(--series-2)"></span>${dual('satélite que mira cada 10 min', 'GOES')}</span><span class="legend-item"><span class="sw sw-sq" style="background:var(--series-1)"></span>${dual('satélites de paso', 'VIIRS/MODIS')}</span><span class="muted">· Toca un gráfico para ir a esa hora.</span></div>
    <div id="case-chart"></div>
    <p class="tiny muted" id="weather-note">Cargando el clima de esas horas…</p>
    <h2 class="section">Momentos clave <span class="tag">${dual('según los satélites', 'derivados de los datos')}</span></h2>
    ${tl.events.length ? html`<ul class="list event-list">${tl.events.map((e, i) => html`<li tabindex="0" data-event="${i}">
      <span class="ev-icon ev-${e.kind}" aria-hidden="true"></span>
      <span class="grow"><span class="event-time">${shortTime(utcDate(e.t))}</span><span class="small">${dual(plainEvent(e), e.label)}</span></span></li>`)}</ul>`
      : html`<p class="small muted">${c.goes_note || 'Sin detecciones para derivar eventos.'} ${firms ? 'Agrega VIIRS/MODIS para completar la reconstrucción.' : ''}</p>`}
    <h2 class="section">En el mapa</h2>
    <div class="switch-row"><div class="grow"><b class="small">${dual('Mostrar la zona con calor', 'Huella acumulada')}</b><div class="tiny muted">${dual('Todo lo que los satélites vieron caliente hasta esa hora. Es aproximada.', tl.footprint_note)}</div></div>
      <label class="switch"><input type="checkbox" id="l-foot" aria-label="Mostrar la zona con calor" ${S.showFootprint ? 'checked' : ''} /><span></span></label></div>
    <div class="x-tech"><div class="btn-row" style="margin-top:12px">
      <label class="btn btn-sm" for="perimeter">⬡ Importar perímetro CONAF (GeoJSON)</label>
      <input type="file" id="perimeter" accept=".geojson,.json,application/geo+json,application/json" hidden />
      <button class="btn btn-sm" id="polar" ${firms ? '' : 'disabled'} title="${firms ? '' : 'Requiere FIRMS_MAP_KEY en el servidor'}">${S.polar.length ? `VIIRS/MODIS: ${fmtNum(S.polar.length)} cargadas` : 'Sumar VIIRS/MODIS (FIRMS)'}</button>
    </div>
    <p class="tiny muted" style="margin-top:6px">El perímetro de IDE Minagri viene en UTM: conviértelo antes con <code>scripts/convert_conaf.py</code>. Se muestra como estado final, no como avance.</p></div>
    <h2 class="section">Qué pasó</h2>
    <ul class="list">${c.context.map((x) => html`<li><span class="grow small">${x.text}</span>${x.verified ? '' : html`<span class="tag tag-verify">por verificar</span>`}</li>`)}</ul>
    <div class="btn-row" style="margin-top:8px">${c.references.map((r) => html`<a class="btn btn-sm btn-ghost" href="${r.url}" target="_blank" rel="noopener">${r.label} ↗</a>`)}</div>
    <p class="tiny muted x-plain" style="margin-top:14px">Datos de satélites de la NASA y la NOAA, y del clima registrado esas horas. Horas en hora de Chile.</p>
    <div class="callout x-tech" style="margin-top:14px"><b>Datos.</b> ${c.goes ? `GOES-16 ABI FDC cada ${c.goes.cadence_min} min (${fmtNum(tl.counts.goes)} píxeles) desde AWS Open Data. ` : `${c.goes_note} `}${S.polar.length ? `VIIRS/MODIS del archivo científico FIRMS (${fmtNum(S.polar.length)}). ` : ''}Clima: reanálisis ERA5. Las horas se muestran en hora de Chile.</div>`);

  const root = container;
  root.querySelector('#pl-play').addEventListener('click', () => togglePlay());
  root.querySelector('#pl-slider').addEventListener('input', (e) => { togglePlay(false); seek(Number(e.target.value)); });
  root.querySelectorAll('[data-speed]').forEach((b) => b.addEventListener('click', () => {
    S.speed = Number(b.dataset.speed);
    root.querySelectorAll('[data-speed]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    if (S.timer) togglePlay(true);
  }));
  const eventTimes = tl.events.map((e) => Math.max(0, S.hourTimes.findIndex((t) => t + 3600000 > utcDate(e.t).getTime())));
  root.querySelector('#pl-prev').addEventListener('click', () => { const prev = eventTimes.filter((i) => i < S.index).pop(); if (prev !== undefined) { togglePlay(false); seek(prev); } });
  root.querySelector('#pl-next').addEventListener('click', () => { const next = eventTimes.find((i) => i > S.index); if (next !== undefined) { togglePlay(false); seek(next); } });
  root.querySelectorAll('[data-event]').forEach((li) => {
    const go = () => {
      const e = tl.events[Number(li.dataset.event)];
      togglePlay(false); seek(eventTimes[Number(li.dataset.event)]);
      if (e.lat) { fly(e.lon, e.lat, 11.5); if (S.globe) S.globe.flyGlobe(e.lon, e.lat, 30000); }
      setData('case-event', e.lat ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [e.lon, e.lat] }, properties: {} }] } : EMPTY);
    };
    li.addEventListener('click', go);
    li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') go(); });
  });
  root.querySelector('#l-foot').addEventListener('change', (e) => { S.showFootprint = e.target.checked; paint(S.index); });
  root.querySelector('#perimeter').addEventListener('change', (e) => { const f = e.target.files[0]; if (f) importPerimeter(f); e.target.value = ''; });
  root.querySelector('#polar').addEventListener('click', () => loadPolar(true));
  root.querySelector('#v3d').addEventListener('click', toggle3D);
  root.querySelector('#v2d').addEventListener('click', show2D);
  setViewButtons(!$('#globe').hidden);
  if (!keepIndex) {
    const first = tl.events.find((e) => e.kind === 'inicio');
    S.index = first ? Math.max(0, S.hourTimes.findIndex((t) => t + 3600000 > utcDate(first.t).getTime())) : 0;
  }
  buildChart();
  seek(S.index);
  loadWeather();
}

let openSeq = 0;
async function openCase(container, id) {
  const mine = ++openSeq;
  container.innerHTML = '<a class="btn btn-sm btn-ghost" href="#/casos">← Historia</a><h1 class="view-title" style="margin-top:12px">Cargando la reconstrucción…</h1><p class="muted small">Descargando detecciones satelitales del caso.</p>';
  let detail; let goes = null;
  try {
    detail = await api.caseDetail(id);
    if (detail.case.goes) goes = await api.caseGoes(id).catch(() => null);
  } catch (err) {
    if (mine === openSeq) container.innerHTML = String(html`<a class="btn btn-sm btn-ghost" href="#/casos">← Historia</a><p class="muted">${err.message}</p>`);
    return;
  }
  if (!mounted || mine !== openSeq) return; // otra navegación ganó
  S = {
    container, case: detail.case, timeline: detail.timeline, index: 0, speed: 3, timer: null, chart: null, globe: null,
    showFootprint: true, weather: null, weatherIndex: [], polar: [],
    goes: goesObservations(goes).sort((a, b) => a.t - b.t),
    hourTimes: detail.timeline.hours.map((h) => utcDate(h.t).getTime()),
  };
  show(['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-event'], true);
  fitBbox(detail.case.bbox, 30);
  legend();
  if (detail.polar_loaded) await loadPolar(false);
  if (mine !== openSeq) return;
  renderCase(container);
}

export default {
  id: 'casos',
  sheet: 'half',
  async mount(container, { rest }) {
    mounted = true;
    openSeq++; // invalida cualquier caso que aún esté cargando (por ejemplo, al volver al catálogo)
    stopPlayback();
    S?.chart?.destroy();
    S = null;
    show(['detections', 'goes-pixels', 'goes-pixels-line', 'risk-fill', 'explore', 'reports', 'places', 'place-radius-fill', 'place-radius-line', 'services'], false);
    $('#map-legend').classList.add('mobile-show');
    container.replaceChildren();
    if (rest?.[0]) await openCase(container, rest[0]); else await renderCatalog(container);
  },
  unmount() {
    mounted = false;
    openSeq++;
    stopPlayback();
    S?.chart?.destroy();
    $('#globe').hidden = true;
    document.querySelector('.map-wrap').classList.remove('globe-on');
    for (const id of ['case-goes', 'case-points', 'case-footprint', 'case-event']) setData(id, EMPTY);
    show(['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-event'], false);
    $('#map-legend').classList.remove('mobile-show');
    S = null;
  },
};

/** Detiene la reproducción sin depender de que haya un caso abierto. */
function stopPlayback() { if (S?.timer) { clearInterval(S.timer); S.timer = null; } }
