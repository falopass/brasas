/* BRASA · widget embebible (web/embed.html, servido en /embed?comuna=…): una tarjeta
 * compacta de solo lectura para la web de un municipio. Riesgo de hoy con su porqué,
 * Botón Rojo e incidentes abiertos de la comuna. Solo GET públicos: sin mapa, sin token,
 * sin localStorage ni datos personales; se refresca sola cada 5 minutos. */

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

/* «hace 12 min», «hace 3 h» (igual que pantalla.js y lite.js). */
function ago(iso, now = Date.now()) {
  if (!iso) return '';
  const minutes = Math.round((now - parseUTC(iso).getTime()) / 60000);
  if (minutes < 1) return 'recién';
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `hace ${hours} h`;
  return `hace ${Math.round(hours / 24)} días`;
}

/* Nombre comparable: minúsculas, sin tildes y con espacios simples (como backend/geo.py: _fold). */
const fold = (s) => s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim().replace(/\s+/g, ' ');

/* «hoy», «mañana» o el día de la semana corto (como dayLabel de pantalla.js). */
function dayLabel(isoDate, today, tomorrow) {
  if (isoDate === today) return 'hoy';
  if (isoDate === tomorrow) return 'mañana';
  return parseUTC(`${isoDate}T12:00:00`).toLocaleDateString('es-CL', { weekday: 'short', day: 'numeric', timeZone: TZ });
}

const LEVEL_LABELS = { bajo: 'Bajo', moderado: 'Moderado', alto: 'Alto', extremo: 'Extremo' };
const LEVEL_PLAIN = {
  bajo: 'El clima no ayuda al fuego. Igual, cuidado con quemas y chispas.',
  moderado: 'Calor o sequedad: un fuego podría avanzar si hay viento.',
  alto: 'Día peligroso: un fuego pequeño puede crecer rápido. No hagas quemas.',
  extremo: 'Muy peligroso: calor, aire seco y viento a la vez. Cualquier chispa puede iniciar un incendio.',
};
const INCIDENT = {
  anomalia: { tag: 'Señal de calor', tone: 'st-aviso' },
  posible: { tag: 'Posible incendio', tone: 'st-riesgo' },
  reportado: { tag: 'Visto por vecinos', tone: 'st-urgente' },
  confirmado: { tag: 'Informado por CONAF', tone: 'st-urgente' },
  controlado: { tag: 'Controlado', tone: 'st-aviso' },
};

async function get(path) {
  let response;
  try {
    response = await fetch(path);
  } catch {
    throw new Error('Sin conexión con el servidor de BRASA.');
  }
  if (!response.ok) throw new Error(`Error ${response.status}`);
  return response.json();
}

/* Índice de comunas (nombre, región, centro y caja), el mismo que usan los buscadores de la app. */
let comunas = null;
async function loadComunas() {
  if (!comunas) comunas = await get('/web/data/comunas-index.json');
  return comunas;
}

function resolveComuna(list, param) {
  if (/^\d+$/.test(param)) return list.find((c) => c.code === Number(param)) || null;
  const wanted = fold(param);
  return list.find((c) => fold(c.name) === wanted) || null;
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

function paint(comuna, risk, incidents) {
  document.title = `BRASA · ${comuna.name}`;
  $('#comuna-name').textContent = comuna.name;
  $('#comuna-region').textContent = comuna.region;
  $('#mas').href = `/#/riesgo?comuna=${comuna.code}`;

  const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: TZ });
  const today = risk?.days?.find((d) => d.date === todayStr);
  const level = today?.level_combined || today?.level || null;
  $('#level-word').textContent = level ? (LEVEL_LABELS[level] || level) : 'Sin dato';
  $('#level').className = `level${level ? ` lv-${level}` : ''}`;
  $('#level-what').textContent = level
    ? `Condiciones para incendios hoy. ${LEVEL_PLAIN[level] || ''}`
    : 'Todavía no hay pronóstico de peligro para hoy en esta comuna.';
  let reasons = [];
  try { reasons = JSON.parse(today?.reasons || '[]'); } catch { reasons = []; }
  $('#level-reasons').replaceChildren(...reasons.slice(0, 3).map((r) => el('li', null, r)));

  const tomorrowStr = new Date(Date.now() + 86400000).toLocaleDateString('en-CA', { timeZone: TZ });
  const brNext = (risk?.boton_rojo || []).find((d) => d.hours > 0);
  $('#br-pill').replaceChildren('Botón Rojo: ',
    brNext ? el('b', null, `${brNext.hours} h ${dayLabel(brNext.date, todayStr, tomorrowStr)}`) : 'no pronosticado');

  const open = (incidents || []).filter((i) => i.comuna_code === comuna.code && i.status !== 'extinguido');
  $('#inc-pill').textContent = open.length
    ? `${open.length} ${open.length === 1 ? 'incidente abierto' : 'incidentes abiertos'}`
    : 'Sin incidentes abiertos';
  $('#inc-list').replaceChildren(...open.slice(0, 4).map((i) => {
    const info = INCIDENT[i.status] || INCIDENT.anomalia;
    const li = el('li');
    li.append(el('span', `tag ${info.tone}`, info.tag), `última señal ${ago(i.last_seen_at)}`);
    return li;
  }));
  $('#inc').hidden = !open.length;
  $('#asof').textContent = risk?.data_as_of ? `· datos ${ago(risk.data_as_of)}` : '';
  $('#widget').hidden = false;
}

let loading = false;
async function load() {
  if (loading) return;
  loading = true;
  try {
    const param = (new URLSearchParams(location.search).get('comuna') || '').trim();
    if (!param) {
      statusMsg('Este widget muestra el riesgo de hoy de una comuna: agrega ?comuna= a la dirección (por ejemplo, ?comuna=5801 o ?comuna=Penco).');
      return;
    }
    const comuna = resolveComuna(await loadComunas(), param);
    if (!comuna) {
      statusMsg(`No encontramos la comuna «${param}». Usa su código (por ejemplo, ?comuna=5801) o su nombre exacto.`);
      return;
    }
    const [risk, incidents] = await Promise.all([
      get(`/api/risk/${comuna.code}`),
      get('/api/incidents?hours=48').catch(() => null),
    ]);
    statusMsg('');
    paint(comuna, risk, incidents?.incidents || []);
  } catch (err) {
    statusMsg(`No se pudo cargar la información de la comuna. ${err.message}`, true);
  } finally {
    loading = false;
  }
}

load();
setInterval(load, REFRESH_MS);
