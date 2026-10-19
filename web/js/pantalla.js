/* BRASA · pantalla pública (web/pantalla.html): página de solo lectura para mirarse a
 * distancia en municipios, cuarteles de Bomberos y colegios (UX-08). Muestra el riesgo
 * de hoy, el Botón Rojo, los avisos DMC y los incendios e incidentes de una comuna.
 * Solo GET públicos: sin mapa, sin token, sin localStorage ni datos personales; se
 * recarga sola cada 5 minutos. */

const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

const TZ = 'America/Santiago';
const REFRESH_MS = 5 * 60 * 1000;
const parseUTC = (s) => new Date(s.endsWith('Z') || s.includes('+') ? s : `${s}Z`);
const fmtTime = (iso) => parseUTC(iso).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
const fmtDateTime = (iso) => parseUTC(iso).toLocaleString('es-CL',
  { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
const fmtNum = (n, digits = 0) => (Number.isFinite(n)
  ? new Intl.NumberFormat('es-CL', { maximumFractionDigits: digits }).format(n) : '—');

/* «hace 12 min», «hace 3 h», «hace 2 días» (igual que lite.js y util.js). */
function ago(iso, now = Date.now()) {
  if (!iso) return 'sin datos';
  const minutes = Math.round((now - parseUTC(iso).getTime()) / 60000);
  if (minutes < 1) return 'recién';
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `hace ${hours} h`;
  return `hace ${Math.round(hours / 24)} días`;
}

/* Nombre comparable: minúsculas, sin tildes y con espacios simples (como backend/geo.py: _fold). */
const fold = (s) => s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim().replace(/\s+/g, ' ');

/* Mismas palabras que RISK de web/js/util.js; las etiquetas vienen de /api/config (risk_levels). */
const LEVEL_LABELS = { bajo: 'Bajo', moderado: 'Moderado', alto: 'Alto', extremo: 'Extremo' };
const LEVEL_PLAIN = {
  bajo: 'El clima no ayuda al fuego. Igual, cuidado con quemas y chispas.',
  moderado: 'Calor o sequedad: un fuego podría avanzar si hay viento.',
  alto: 'Día peligroso: un fuego pequeño puede crecer rápido. No hagas quemas.',
  extremo: 'Muy peligroso: mucho calor, aire seco y viento a la vez. Cualquier chispa puede iniciar un incendio.',
};

/* Etiquetas cortas de los estados de incidente (web/js/views/incendio.js). */
const INCIDENT = {
  anomalia: { tag: 'Señal de calor', tone: 'st-aviso' },
  posible: { tag: 'Posible incendio', tone: 'st-riesgo' },
  reportado: { tag: 'Visto por vecinos', tone: 'st-urgente' },
  confirmado: { tag: 'Informado por CONAF', tone: 'st-urgente' },
  controlado: { tag: 'Controlado', tone: 'st-aviso' },
  extinguido: { tag: 'Extinguido', tone: 'st-tranquilo' },
};
const OFFICIAL_TONE = { confirmado: 'st-urgente', controlado: 'st-aviso', extinguido: 'st-tranquilo' };

class ApiFail extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function get(path) {
  let response;
  try {
    response = await fetch(path);
  } catch {
    throw new ApiFail('Sin conexión con el servidor de BRASA.', 0);
  }
  if (!response.ok) throw new ApiFail(`Error ${response.status}`, response.status);
  return response.json();
}

/* Índice de comunas (nombre, región, centro y caja), el mismo que usa la app para sus buscadores. */
let comunas = null;
async function loadComunas() {
  if (comunas) return comunas;
  const index = await get('/web/data/comunas-index.json');
  comunas = index.sort((a, b) => a.name.localeCompare(b.name, 'es'));
  return comunas;
}

function fillSelect(list, current) {
  const select = $('#comuna-select');
  const first = el('option', null, 'Elige una comuna…');
  first.value = '';
  first.disabled = true;
  if (!current) first.selected = true;
  select.replaceChildren(first, ...list.map((c) => {
    const o = el('option', null, `${c.name} · ${c.region}`);
    o.value = c.code;
    if (current && c.code === current.code) o.selected = true;
    return o;
  }));
  select.hidden = false;
  $('#refresh').hidden = false;
  if (!select.dataset.wired) {
    select.dataset.wired = '1';
    select.addEventListener('change', () => {
      if (!select.value) return;
      const url = new URL(location.href);
      url.searchParams.set('comuna', select.value);
      location.href = url.toString();
    });
  }
}

function resolveComuna(list, param) {
  if (/^\d+$/.test(param)) return list.find((c) => c.code === Number(param)) || null;
  const wanted = fold(param);
  return list.find((c) => fold(c.name) === wanted) || null;
}

/* Incendio «que toca la comuna»: el nombre que reporta CONAF o el punto dentro de su caja.
 * shortcut: la caja es rectangular y puede incluir bordes de comunas vecinas; si se
 * reportan falsos positivos, cruzar con el polígono de web/data/comunas.geojson. */
function fireTouches(fire, comuna) {
  if (fire.comuna && fold(fire.comuna) === fold(comuna.name)) return true;
  const [w, s, e, n] = comuna.bbox;
  return fire.lon >= w && fire.lon <= e && fire.lat >= s && fire.lat <= n;
}

function statusMsg(text, retry = false) {
  const box = $('#status');
  box.classList.toggle('error', retry);
  box.replaceChildren();
  if (text) box.append(text);
  if (retry) {
    const btn = el('button', 'retry', 'Reintentar');
    btn.type = 'button';
    btn.addEventListener('click', load);
    box.append(el('br'), btn);
  }
}

function dayLabel(isoDate, today, tomorrow) {
  if (isoDate === today) return 'hoy';
  if (isoDate === tomorrow) return 'mañana';
  return parseUTC(`${isoDate}T12:00:00`).toLocaleDateString('es-CL', { weekday: 'short', day: 'numeric', timeZone: TZ });
}

function paintHero(comuna, risk, riskLevels) {
  $('#comuna-name').textContent = `${comuna.name} · ${comuna.region}`;
  const date = new Date().toLocaleDateString('es-CL',
    { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: TZ });
  $('#hero-date').textContent = date.charAt(0).toUpperCase() + date.slice(1);
  const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: TZ });
  const today = risk?.days?.find((d) => d.date === todayStr);
  const level = today?.level_combined || today?.level || null;
  const word = $('#level-word');
  word.textContent = level ? (riskLevels[level] || level) : 'Sin dato';
  $('#level').className = `level${level ? ` lv-${level}` : ''}`;
  $('#level-what').textContent = level
    ? `Condiciones para incendios hoy. ${LEVEL_PLAIN[level] || ''}`
    : 'Todavía no hay pronóstico de peligro para hoy en esta comuna.';
  let reasons = [];
  try { reasons = JSON.parse(today?.reasons || '[]'); } catch { reasons = []; }
  $('#level-reasons').replaceChildren(...reasons.map((r) => el('li', null, r)));
  const rain = risk?.rain;
  const note = $('#rain-note');
  if (rain?.plain) { note.textContent = `Lluvia de la temporada: ${rain.plain}`; note.hidden = false; }
  else note.hidden = true;
  $('#hero').hidden = false;
}

function paintBotonRojo(list) {
  const now = new Date();
  const today = now.toLocaleDateString('en-CA', { timeZone: TZ });
  const tomorrow = new Date(now.getTime() + 86400000).toLocaleDateString('en-CA', { timeZone: TZ });
  const entries = (list || []).filter((d) => d.hours > 0);
  const todayEntry = entries.find((d) => d.date === today);
  $('#br-hours').textContent = entries.length
    ? (todayEntry ? `${todayEntry.hours} h hoy` : 'Hoy sin Botón Rojo')
    : 'Sin Botón Rojo pronosticado';
  $('#br-days').replaceChildren(...entries.map((d) => {
    const li = el('li');
    li.append(`${dayLabel(d.date, today, tomorrow)}: `, el('b', null, `${d.hours} h`),
      d.proportion ? ` · ${fmtNum(Math.round(d.proportion * 100))} % de la comuna` : '');
    return li;
  }));
  $('#br-sec').hidden = false;
}

function paintDmc(alerts) {
  const list = $('#dmc-list');
  if (alerts === null) {
    list.replaceChildren(el('li', 'muted', 'No se pudieron cargar los avisos de la DMC.'));
  } else if (!alerts.length) {
    list.replaceChildren(el('li', 'muted', 'Sin avisos de viento o calor extremo vigentes en la comuna.'));
  } else {
    list.replaceChildren(...alerts.map((a) => {
      const li = el('li');
      const tone = /extrem|sever/i.test(a.severity || '') ? 'st-urgente' : 'st-riesgo';
      li.append(el('span', `tag ${tone}`, a.label || 'Aviso'), el('b', null, a.headline || a.event || 'Aviso de la DMC'));
      li.append(el('p', 'meta', a.expires ? `Vigente hasta ${fmtDateTime(a.expires)}` : 'Vigente'));
      return li;
    }));
  }
  $('#dmc-sec').hidden = false;
}

function paintFires(fires, comuna) {
  const list = $('#fires-list');
  if (fires === null) {
    list.replaceChildren(el('li', 'muted', 'No se pudo cargar el reporte de CONAF.'));
  } else if (!fires.length) {
    list.replaceChildren(el('li', 'muted', 'CONAF no informa incendios en la comuna en las últimas 48 h.'));
  } else {
    list.replaceChildren(...fires.map((f) => {
      const li = el('li');
      li.append(el('span', `tag ${OFFICIAL_TONE[f.status] || 'st-riesgo'}`, f.status_raw || f.status),
        el('b', null, `«${f.name || 'sin nombre'}»`));
      const meta = [`empezó ${ago(f.started_at)}`];
      if (f.area_ha) meta.push(`${fmtNum(f.area_ha, f.area_ha < 10 ? 1 : 0)} ha`);
      if (f.comuna && fold(f.comuna) !== fold(comuna.name)) meta.push(`CONAF la registra en ${f.comuna}`);
      li.append(el('p', 'meta', meta.join(' · ')));
      return li;
    }));
  }
  $('#fires-sec').hidden = false;
}

function paintIncidents(incidents) {
  const list = $('#inc-list');
  if (incidents === null) {
    list.replaceChildren(el('li', 'muted', 'No se pudieron cargar las detecciones satelitales.'));
  } else if (!incidents.length) {
    list.replaceChildren(el('li', 'muted', 'Los satélites no vieron calor en la comuna en las últimas 48 h.'));
  } else {
    list.replaceChildren(...incidents.slice(0, 10).map((i) => {
      const info = INCIDENT[i.status] || INCIDENT.anomalia;
      const li = el('li');
      li.append(el('span', `tag ${info.tone}`, info.tag));
      const meta = [`última señal ${ago(i.last_seen_at)}`, `${fmtNum(i.n_obs)} ${i.n_obs === 1 ? 'detección' : 'detecciones'}`];
      li.append(el('p', 'meta', meta.join(' · ')));
      return li;
    }));
  }
  $('#inc-sec').hidden = false;
}

function stampRefreshed() {
  $('#refreshed').textContent = `Actualizado ${new Date().toLocaleTimeString('es-CL',
    { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ })} · se refresca solo cada 5 min`;
}

let loading = false;
async function load() {
  if (loading) return;
  loading = true;
  try {
    let list;
    try {
      list = await loadComunas();
    } catch (err) {
      statusMsg(`No se pudo cargar la lista de comunas. ${err.message}`, true);
      return;
    }
    const param = (new URLSearchParams(location.search).get('comuna') || '').trim();
    const comuna = param ? resolveComuna(list, param) : null;
    fillSelect(list, comuna);
    if (!param) {
      statusMsg('Esta pantalla muestra el riesgo de hoy de una comuna. Elige una en la lista de arriba o agrega ?comuna= a la dirección (por ejemplo, ?comuna=13101 o ?comuna=Santiago).');
      return;
    }
    if (!comuna) {
      statusMsg(`No encontramos la comuna «${param}». Elige una de la lista de arriba.`);
      return;
    }
    statusMsg('Cargando…');
    const [risk, official, incidents, config] = await Promise.all([
      get(`/api/risk/${comuna.code}`),
      get('/api/official-fires?hours=48').catch(() => null),
      get('/api/incidents?hours=48').catch(() => null),
      get('/api/config').catch(() => null),
    ]);
    statusMsg('');
    paintHero(comuna, risk, { ...LEVEL_LABELS, ...(config?.risk_levels || {}) });
    paintBotonRojo(risk.boton_rojo);
    paintDmc(risk.dmc_alerts ?? []);
    paintFires(official ? official.fires.filter((f) => fireTouches(f, comuna)) : null, comuna);
    paintIncidents(incidents ? incidents.incidents.filter((i) => i.comuna_code === comuna.code) : null);
    const asof = $('#asof');
    asof.textContent = `Datos: ${ago(risk.data_as_of)}`;
    asof.hidden = false;
    stampRefreshed();
  } catch (err) {
    statusMsg(`No se pudo cargar la información de la comuna. ${err.message}`, true);
  } finally {
    loading = false;
  }
}

$('#refresh').addEventListener('click', load);
load();
setInterval(load, REFRESH_MS);
