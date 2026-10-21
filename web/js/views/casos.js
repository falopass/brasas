/* Casos históricos: reconstrucción hora a hora con detecciones reales, huella acumulada, clima ERA5 y eventos.
 * Un solo reloj (índice horario) sincroniza el mapa 2D, la vista 3D, los gráficos y la lista de eventos. */
import { api, request } from '../api.js';
import { timeChart } from '../charts.js';
import { errorConSalida } from '../errores.js';
import { fitBbox, fly, setData, show } from '../map.js';
import { codeDeComuna, filterNominados, sumHa } from '../nominados.js';
import { sliderUrl, worldviewLayer, worldviewUrl } from '../satelite.js';
import { store } from '../store.js';
import { $, dual, fmtDay, fmtNum, haversineKm, html, pixelSquare, TZ, TZ_LABEL, toast } from '../util.js';

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

const SCOPE = { fire: 'Un incendio', complex: 'Varios focos unidos', episode: 'Muchos incendios a la vez', season: 'Temporada completa' };
const fmtRevDate = (d) => (/^\d{4}-\d{2}-\d{2}$/.test(d) ? fmtDay(d, { weekday: undefined, year: 'numeric' }) : /^\d{4}-\d{2}$/.test(d) ? d.split('-').reverse().join('-') : d);

/** Cifras con su historia: la última revisión en grande y, debajo, cómo cambió y quién la informó. */
function figuresHtml(figures) {
  if (!figures?.length) return '';
  const KIND_LABEL = { oficial: 'Oficial', estudio: 'Estudio' };
  const kindTag = (r) => html`<span class="tag${r.kind === 'oficial' ? ' tag-live' : ''}">${KIND_LABEL[r.kind] || 'Prensa'}</span>`;
  return html`<h2 class="section">Las cifras <span class="tag">${dual('con su fuente', 'revisiones con fuente y fecha')}</span></h2>
    <div class="figures">${figures.map((f) => {
      const last = f.revisions[f.revisions.length - 1];
      return html`<div class="figure-row"><small>${f.label}</small><strong>${last.value}</strong>
        <span class="tiny muted">${kindTag(last)} ${last.source} · ${fmtRevDate(last.date)}${last.note ? ` · ${last.note}` : ''} <a href="${last.url}" target="_blank" rel="noopener">Ver ↗</a></span>
        ${f.revisions.length > 1 ? html`<details class="fold fold-sm"><summary>Cómo cambió esta cifra (${f.revisions.length})</summary><ul>${f.revisions.map((r) => html`<li class="small"><b>${r.value}</b> · ${kindTag(r)} ${r.source} · ${fmtRevDate(r.date)}${r.note ? html`<span class="tiny muted"> · ${r.note}</span>` : ''} <a href="${r.url}" target="_blank" rel="noopener">↗</a></li>`)}</ul></details>` : ''}</div>`;
    })}</div>
    <p class="tiny muted">${dual('Las cifras cambian a medida que se cuentan los daños. «Oficial» sale directo del sitio del servicio público; «Prensa» es un medio que puede citar a CONAF o SENAPRED; «Estudio» es un informe de investigación. Para un dato definitivo, revisa CONAF o SENAPRED.', 'Cifras ordenadas por fecha. «Oficial» enlaza directo a un servicio público chileno; «Prensa» es un medio, aunque cite a CONAF, SENAPRED o la Fiscalía; «Estudio» es un centro de investigación o academia. Superficie de complejos y episodios no es comparable con la de un incendio único.')}</p>`;
}

/** Enlaces a visores satelitales externos sobre el área y la fecha del caso (nueva pestaña). */
function satelliteLinks(c) {
  const wv = worldviewUrl({ bbox: c.bbox, start: c.start_utc, end: c.end_utc });
  const slider = sliderUrl({ satellite: c.goes?.satellite });
  if (!wv && !slider) return '';
  const tech = [
    wv ? `Worldview muestra la capa ${worldviewLayer(c.start_utc)} del ${c.start_utc.slice(0, 10)} ${c.start_utc.slice(11, 16)} UTC` : '',
    slider ? `SLIDER abre el disco completo de GOES-${c.goes.satellite.slice(1)}` : '',
  ].filter(Boolean).join('; ');
  return html`<div class="btn-row" style="margin:2px 0 10px">
    ${wv ? html`<a class="btn btn-sm btn-ghost" href="${wv}" target="_blank" rel="noopener">${dual('Ver el humo', 'NASA Worldview · imagen del día del caso')} ↗</a>` : ''}
    ${slider ? html`<a class="btn btn-sm btn-ghost" href="${slider}" target="_blank" rel="noopener">${dual('Ver el satélite en acción', `SLIDER · GOES-${c.goes.satellite.slice(1)}`)} ↗</a>` : ''}
    <span class="tiny muted" style="align-self:center">${dual('Abre otra pestaña y pesa unos MB.', `${tech}.`)}</span></div>`;
}

// ------------------------------------------------- incendios nominados (CONAF-GEPRIF)
const NOM_MAX = 80; // tope de filas visibles por filtro
let nominadosPromise = null;
let comunasPromise = null;

/** Una fila de nominados: la comuna enlaza a su ficha de riesgo si el índice la resuelve; si no, texto plano. */
export function filaNominado(i, index, season = '') {
  const code = codeDeComuna(index, i.comuna);
  const comuna = code
    ? html`<a href="#/riesgo?comuna=${code}" aria-label="Ver el riesgo de ${i.comuna}">${i.comuna}</a>`
    : i.comuna;
  return html`<li class="small"><b>${i.name}</b> · ${comuna} · ${fmtNum(i.ha, 1)} ha${season ? '' : ` · ${i.season}`}</li>`;
}

function paintNominados(list, meta, items, { comuna = '', season = '', index = [] } = {}) {
  const rows = filterNominados(items, { comuna, season });
  list.innerHTML = String(html`${rows.slice(0, NOM_MAX).map((i) => filaNominado(i, index, season))}`);
  if (!rows.length) {
    meta.textContent = `No hay incendios nominados${comuna.trim() ? ` en «${comuna.trim()}»` : ''}${season ? ` en la temporada ${season}` : ''}.`;
    return;
  }
  meta.textContent = rows.length > NOM_MAX
    ? `${fmtNum(rows.length)} incendios · ${fmtNum(sumHa(rows), 1)} ha en total; se muestran las ${NOM_MAX} más grandes y ${fmtNum(rows.length - NOM_MAX)} quedan fuera del recorte.`
    : `${fmtNum(rows.length)} incendios · ${fmtNum(sumHa(rows), 1)} ha en total.`;
}

/** Índice territorial para enlazar cada comuna: el que ya cargó el mapa o uno liviano, una sola vez.
 * Si falla, la lista se pinta igual con texto plano: nunca se inventa un código. */
async function comunasIndex() {
  const cached = store.get('comunasIndex');
  if (Array.isArray(cached) && cached.length) return cached;
  if (!comunasPromise) {
    comunasPromise = request('/web/data/comunas-index.json')
      .then((index) => {
        if (Array.isArray(index) && index.length) store.set('comunasIndex', index);
        return Array.isArray(index) ? index : [];
      })
      .catch(() => []);
  }
  return comunasPromise;
}

/** Carga la lista la primera vez que se abre el bloque; después solo repinta al filtrar. */
async function openNominados(details) {
  if (!nominadosPromise) nominadosPromise = request('/web/data/incendios-nominados.json');
  const select = details.querySelector('#nom-season');
  const input = details.querySelector('#nom-comuna');
  const clear = details.querySelector('#nom-clear');
  const list = details.querySelector('#nom-list');
  const meta = details.querySelector('#nom-meta');
  try {
    const [data, index] = await Promise.all([nominadosPromise, comunasIndex()]);
    if (!details.isConnected) return;
    const repaint = () => paintNominados(list, meta, data.items, { comuna: input.value, season: select.value, index });
    if (data.coverage?.to) {
      details.querySelector('#nom-coverage').textContent =
        `La serie cubre las temporadas ${data.coverage.from} a ${data.coverage.to}: es la última que publica la capa oficial de CONAF-GEPRIF, así que las temporadas siguientes todavía no aparecen.`;
    }
    if (!select.options.length) {
      const seasons = [...new Set(data.items.map((i) => i.season))].sort().reverse();
      select.innerHTML = String(html`<option value="">Todas las temporadas (las más grandes)</option>${seasons.map((s) => html`<option value="${s}">Temporada ${s}</option>`)}`);
      select.addEventListener('change', repaint);
      input.addEventListener('input', repaint);
      clear.addEventListener('click', () => { input.value = ''; repaint(); input.focus(); });
    }
    repaint();
  } catch (err) {
    meta.textContent = `No se pudo cargar la lista (${err.message}).`;
  }
}

// ------------------------------------------------------------------ catálogo
const CATALOG_BBOX = [-74.5, -39.5, -70, -32]; // encuadre histórico del catálogo completo

/** Regiones de un caso: el dato puede traer varias separadas por comas y « y » («Ñuble, Biobío y La Araucanía»). */
const regionesDel = (c) => String(c.region || '').split(/\s*,\s*|\s+y\s+/).map((r) => r.trim()).filter(Boolean);

/** Regiones únicas del catálogo, en el orden en que aparecen en el archivo. */
export function regionesDe(cases) {
  return [...new Set(cases.flatMap(regionesDel))];
}

/** Casos cuya región incluye la elegida; «Todas» (o vacío) devuelve el catálogo completo. */
export function filtrarPorRegion(cases, region) {
  if (!region || region === 'Todas') return [...cases];
  return cases.filter((c) => regionesDel(c).includes(region));
}

/** La región guardada en el hash de la vista («#/casos?region=Maule» → «Maule»; sin filtro → «»). */
export function regionFromHash(hash) {
  return new URLSearchParams(String(hash || '').split('?')[1] || '').get('region') || '';
}

const centroBbox = (c) => ({ lon: (c.bbox[0] + c.bbox[2]) / 2, lat: (c.bbox[1] + c.bbox[3]) / 2 });
const distanciaCaso = (c, place) => (c.bbox ? haversineKm(place.lat, place.lon, centroBbox(c).lat, centroBbox(c).lon) : Infinity);

/** Casos del más cercano al más lejano respecto al lugar guardado; sin lugar, el orden del archivo. */
export function ordenarPorCercania(cases, place) {
  if (!place || !Number.isFinite(place.lat) || !Number.isFinite(place.lon)) return [...cases];
  return [...cases].sort((a, b) => distanciaCaso(a, place) - distanciaCaso(b, place));
}

/** Caja que encierra los casos filtrados ([oeste, sur, este, norte]); null si la lista viene vacía. */
const unionBbox = (cases) => cases.reduce((u, c) => (c.bbox ? (u ? [Math.min(u[0], c.bbox[0]), Math.min(u[1], c.bbox[1]), Math.max(u[2], c.bbox[2]), Math.max(u[3], c.bbox[3])] : [...c.bbox]) : u), null);

/** Tarjeta del catálogo: un enlace de verdad, así abre con Enter, Ctrl+clic o «copiar enlace». */
export function tarjetaHtml(c, km = null) {
  return html`<a class="card clickable case-card" href="#/casos/${c.id}" style="text-decoration:none">
    <span class="case-year" aria-hidden="true">${c.start_utc.slice(0, 4)}</span>
    <div class="card-title">${c.title}</div><div class="card-sub">${c.subtitle}${c.scope ? ` · ${SCOPE[c.scope]}` : ''}</div>
    <div class="tiny muted" style="margin-top:4px">${fmtDay(c.start_utc.slice(0, 10))} → ${fmtDay(c.end_utc.slice(0, 10))}</div>
    <div class="badges">${Number.isFinite(km) ? html`<span class="tag">a ${fmtNum(Math.round(km))} km de tu lugar</span>` : ''}${c.goes ? html`<span class="tag tag-live">${dual(`Imágenes cada ${c.goes.cadence_min} min`, `GOES-${c.goes.satellite.slice(1)} · cada ${c.goes.cadence_min} min`)}</span>` : html`<span class="tag">${dual('Pocas imágenes', 'Sin GOES')}</span>`}
      <span class="tag x-tech">VIIRS/MODIS (FIRMS)</span><span class="tag">${dual('Clima de esas horas', 'Clima ERA5')}</span></div>
  </a>`;
}

async function renderCatalog(container) {
  let data;
  try { data = await api.cases(); } catch (err) { errorConSalida(container, err, () => renderCatalog(container)); return; }
  show(['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-perimeter', 'case-event'], false);
  const regiones = regionesDe(data.cases);
  const pedida = regionFromHash(location.hash);
  const filtro = regiones.includes(pedida) ? pedida : ''; // una región que no existe equivale a «Todas»
  const place = store.get('places')?.[0];
  const visibles = ordenarPorCercania(filtrarPorRegion(data.cases, filtro), place);
  fitBbox((filtro ? unionBbox(visibles) : null) ?? CATALOG_BBOX, 40);
  $('#map-legend').innerHTML = '';
  container.innerHTML = String(html`
    <h1 class="view-title">Grandes incendios, hora a hora</h1>
    <p class="lede">${dual('Mira cómo avanzaron seis incendios que marcaron a Chile: lo que vieron los satélites, el viento y el calor de esas horas. Todo con datos reales.', 'Reconstrucción con detecciones satelitales reales, huella acumulada, clima ERA5 y eventos derivados. Sin datos inventados.')}</p>
    <div class="btn-row" role="group" aria-label="Filtrar por región" style="margin:2px 0 10px">
      <button class="chip" type="button" data-region="" aria-pressed="${String(!filtro)}">Todas</button>
      ${regiones.map((r) => html`<button class="chip" type="button" data-region="${r}" aria-pressed="${String(r === filtro)}">${r}</button>`)}
    </div>
    ${visibles.map((c, i) => tarjetaHtml(c, place && i === 0 ? distanciaCaso(c, place) : null))}
    <div class="callout" style="margin-top:14px"><b>Cómo leerlo.</b> ${dual('Los satélites ven calor, no el borde exacto del fuego, y el humo espeso a veces lo tapa. Por eso la zona marcada es aproximada: suele verse más grande que lo que realmente se quemó.', 'Los satélites registran píxeles calientes en cada pasada; no ven el perímetro ni el fuego bajo humo denso. La huella acumulada sobreestima la superficie, sobre todo con GOES (2–3 km). Para la superficie oficial, importa el perímetro de CONAF.')}</div>
    <details class="fold" id="nom-details" style="margin-top:14px"><summary>${dual('Incendios con nombre propio (de 50 ha o más)', 'Incendios nominados (≥50 ha)')}</summary>
      <div>
        <p class="small muted">${dual('Cada incendio de 50 hectáreas o más que CONAF registró con nombre, con su comuna y la superficie que alcanzó. Se ordenan de mayor a menor.', 'Puntos de inicio ≥50 ha de la capa PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA: nombre, comuna, temporada y superficie registrada. Una fila por nombre+temporada+comuna (la de mayor superficie).')} La comuna es la del registro de CONAF; el punto de inicio puede caer en la comuna vecina.</p>
        <p class="tiny muted" id="nom-coverage"></p>
        <div class="field" style="margin-bottom:6px"><label for="nom-comuna">Buscar por comuna</label>
          <input class="input" id="nom-comuna" type="search" placeholder="Escribe, por ejemplo: Quirihue" autocomplete="off" /></div>
        <div class="btn-row" style="margin-bottom:8px">
          <select class="input" id="nom-season" aria-label="Filtrar por temporada"></select>
          <button class="btn btn-sm btn-ghost" id="nom-clear" type="button">Limpiar</button></div>
        <ul id="nom-list"></ul>
        <p class="tiny muted" id="nom-meta">La lista se carga al abrir este bloque.</p>
        <p class="tiny muted">Fuente: <a href="https://deigeprif.com" target="_blank" rel="noopener">CONAF-GEPRIF</a> · uso público con cita</p>
      </div>
    </details>
    <p class="tiny muted x-tech" style="margin-top:10px">${data.note}</p>`);
  container.querySelectorAll('[data-region]').forEach((chip) => {
    chip.addEventListener('click', () => {
      const r = chip.dataset.region;
      location.hash = r ? `#/casos?region=${encodeURIComponent(r)}` : '#/casos';
    });
  });
  const nomDetails = container.querySelector('#nom-details');
  nomDetails.addEventListener('toggle', () => { if (nomDetails.open) openNominados(nomDetails); });
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
    S.container.querySelector('#weather-note').innerHTML = String(dual('El clima de esas horas no está disponible ahora. Vuelve a intentarlo más tarde.', html`Clima ERA5 no disponible ahora (${err.message}). Se cargará cuando el servidor tenga conexión con Open-Meteo.`));
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
    S.polarCount = points.length;
    S.polar = polarObservations(points).sort((a, b) => a.t - b.t);
    if (force) {
      const detail = await api.caseDetail(id);
      if (S !== mine) return;
      S.timeline = detail.timeline;
      renderCase(S.container, true);
    }
  } catch (err) { if (force && S === mine) toast(err.message, 'error'); }
}

/** Perímetro oficial CONAF (capa aparte, apagada por defecto): se descarga solo al encenderla. */
async function togglePerimeter(input) {
  if (!input.checked) {
    show('case-perimeter', false);
    return;
  }
  const mine = S;
  try {
    if (!S.perimeter) S.perimeter = await request(`/web/data/cases/${S.case.id}.perimeter.json`);
    if (S !== mine) return;
    setData('case-perimeter', S.perimeter);
    show('case-perimeter', true);
  } catch (err) {
    if (S !== mine) return;
    input.checked = false;
    toast(`No se pudo cargar el perímetro oficial (${err.message}).`, 'error');
  }
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
      ${S.case.perimeter ? html`<span class="legend-item"><span class="sw sw-line" style="color:#1b9e77;border-top-style:solid"></span>${dual('Borde oficial', 'Perímetro oficial CONAF — GEPRIF')}</span>` : ''}
      <span class="legend-item x-tech"><span class="sw sw-line"></span>Perímetro importado</span></div>
    <div class="legend-note">${dual('Es lo que vieron los satélites, no el borde oficial del incendio.', 'Huella = píxeles calientes observados, no perímetro oficial.')}</div>`);
}

function renderCase(container, keepIndex = false) {
  const c = S.case;
  const tl = S.timeline;
  const firms = store.get('config')?.firms_configured;
  const detections = S.goes.length + S.polarCount;
  container.innerHTML = String(html`
    <a class="btn btn-sm btn-ghost" href="#/casos">← Historia</a>
    <h1 class="view-title">${c.title}</h1>
    <p class="lede">${c.subtitle} · ${fmtDay(c.start_utc.slice(0, 10))} → ${fmtDay(c.end_utc.slice(0, 10))}${c.scope ? ` · ${SCOPE[c.scope].toLowerCase()}` : ''}</p>
    ${satelliteLinks(c)}
    ${detections ? html`<div class="btn-row" style="margin:2px 0 10px">
      <a class="btn btn-sm btn-ghost" href="/api/cases/${c.id}/export.csv" download>Descargar CSV</a>
      <span class="tiny muted" style="align-self:center">${dual(`${fmtNum(detections)} detecciones, una por fila: hora, lugar, satélite y fuerza. Se abre en Excel o cualquier planilla.`, `${fmtNum(detections)} filas · columnas: hora UTC y de Chile, lat/lon, sensor, satélite, confianza, FRP y fuente (goes/polar)`)}</span></div>` : ''}
    <div class="player" role="group" aria-label="Reproductor de la reconstrucción">
      <div class="player-time"><strong id="pl-time"></strong><span class="tiny muted x-tech" id="pl-utc"></span></div>
      <div class="player-controls">
        <button class="play-btn" id="pl-play" aria-label="Reproducir"></button>
        <input type="range" id="pl-slider" min="0" max="${S.hourTimes.length - 1}" step="1" value="0" aria-label="Hora de la reconstrucción" />
        <button class="btn btn-sm" id="pl-prev" aria-label="‹ Antes: momento clave anterior">‹ Antes</button><button class="btn btn-sm" id="pl-next" aria-label="Después ›: momento clave siguiente">Después ›</button>
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
    ${c.perimeter ? html`<div class="switch-row"><div class="grow"><b class="small">${dual('El borde oficial del incendio', 'Perímetro oficial CONAF')}</b><div class="tiny muted">${dual('El límite que CONAF midió al cerrar el incendio: lo que realmente se quemó.', 'Perímetros oficiales del compilado operativo CONAF 2014-2025, simplificados para la web.')} Fuente: CONAF — GEPRIF.</div></div>
      <label class="switch"><input type="checkbox" id="l-perim" aria-label="Mostrar el perímetro oficial de CONAF" /><span></span></label></div>` : ''}
    <div class="x-tech"><div class="btn-row" style="margin-top:12px">
      <label class="btn btn-sm" for="perimeter">⬡ Importar perímetro CONAF (GeoJSON)</label>
      <input type="file" id="perimeter" accept=".geojson,.json,application/geo+json,application/json" hidden />
      <button class="btn btn-sm" id="polar" ${firms ? '' : 'disabled'} title="${firms ? '' : 'Requiere FIRMS_MAP_KEY en el servidor'}">${S.polar.length ? `VIIRS/MODIS: ${fmtNum(S.polar.length)} cargadas` : 'Sumar VIIRS/MODIS (FIRMS)'}</button>
    </div>
    <p class="tiny muted" style="margin-top:6px">El perímetro de IDE Minagri viene en UTM: conviértelo antes con <code>scripts/convert_conaf.py</code>. Se muestra como estado final, no como avance.</p></div>
    ${figuresHtml(c.figures)}
    <h2 class="section">Qué pasó</h2>
    <ul class="list">${c.context.map((x) => html`<li><span class="grow small">${x.text}</span>${x.verified ? '' : html`<span class="tag tag-verify">por verificar</span>`}</li>`)}</ul>
    <div class="btn-row" style="margin-top:8px">${c.references.map((r) => html`<a class="btn btn-sm btn-ghost" href="${r.url}" target="_blank" rel="noopener">${r.label} ↗</a>`)}</div>
    ${c.lessons?.length ? html`<h2 class="section">Lecciones</h2>
    <ul class="list">${c.lessons.map((l) => html`<li><span class="grow small">${l.text}<br /><span class="tiny muted">Fuente: <a href="${l.url}" target="_blank" rel="noopener">${l.source} ↗</a></span></span></li>`)}</ul>` : ''}
    <p class="tiny muted x-plain" style="margin-top:14px">Datos de satélites de la NASA y la NOAA, y del clima registrado esas horas. Horas en ${TZ_LABEL}.</p>
    <div class="callout x-tech" style="margin-top:14px"><b>Datos.</b> ${c.goes ? `GOES-${c.goes.satellite.slice(1)} ABI FDC cada ${c.goes.cadence_min} min (${fmtNum(tl.counts.goes)} píxeles) desde AWS Open Data. ` : `${c.goes_note} `}${S.polar.length ? `VIIRS/MODIS del archivo científico FIRMS (${fmtNum(S.polar.length)}). ` : ''}Clima: reanálisis ERA5. Las horas se muestran en ${TZ_LABEL}.</div>`);

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
  root.querySelector('#l-perim')?.addEventListener('change', (e) => togglePerimeter(e.target));
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
    if (mine === openSeq) {
      container.innerHTML = '<a class="btn btn-sm btn-ghost" href="#/casos">← Historia</a><div id="case-err"></div>';
      errorConSalida(container.querySelector('#case-err'), err, () => openCase(container, id));
    }
    return;
  }
  if (!mounted || mine !== openSeq) return; // otra navegación ganó
  S = {
    container, case: detail.case, timeline: detail.timeline, index: 0, speed: 3, timer: null, chart: null, globe: null,
    showFootprint: true, weather: null, weatherIndex: [], polar: [], polarCount: 0, perimeter: null,
    goes: goesObservations(goes).sort((a, b) => a.t - b.t),
    hourTimes: detail.timeline.hours.map((h) => utcDate(h.t).getTime()),
  };
  show(['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-event'], true);
  setData('case-perimeter', EMPTY); // el perímetro oficial parte apagado en cada caso
  show('case-perimeter', false);
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
    for (const id of ['case-goes', 'case-points', 'case-footprint', 'case-event', 'case-perimeter']) setData(id, EMPTY);
    show(['case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final', 'case-perimeter', 'case-event'], false);
    $('#map-legend').classList.remove('mobile-show');
    S = null;
  },
};

/** Detiene la reproducción sin depender de que haya un caso abierto. */
function stopPlayback() { if (S?.timer) { clearInterval(S.timer); S.timer = null; } }
