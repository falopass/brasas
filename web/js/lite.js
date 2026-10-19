/* BRASA · modo liviano (web/lite.html): página mínima sin mapa para celulares de gama baja y
 * señal lenta. Sin dependencias ni vistas de la app: lee el token del dispositivo
 * (localStorage «brasa:token») y reusa la API. Es de solo lectura: sin token muestra el
 * estado vacío y no llama a la API ni crea suscriptores nuevos. */

const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

/* Tema: la preferencia guardada en la app (por defecto, oscuro como el resto de BRASA). */
try {
  const saved = JSON.parse(localStorage.getItem('brasa:theme'));
  document.documentElement.dataset.theme = saved || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
} catch { document.documentElement.dataset.theme = 'dark'; }

const fmtNum = (n, digits = 0) => (Number.isFinite(n)
  ? new Intl.NumberFormat('es-CL', { maximumFractionDigits: digits }).format(n)
  : '—');

const parseUTC = (s) => new Date(s.endsWith('Z') || s.includes('+') ? s : `${s}Z`);
const TZ = 'America/Santiago';
const fmtDateTime = (iso) => parseUTC(iso).toLocaleString('es-CL',
  { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });

/* «hace 12 min», «hace 3 h», «hace 2 días» (igual que util.js). */
function ago(iso, now = Date.now()) {
  if (!iso) return 'sin datos';
  const minutes = Math.round((now - parseUTC(iso).getTime()) / 60000);
  if (minutes < 1) return 'recién';
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `hace ${hours} h`;
  return `hace ${Math.round(hours / 24)} días`;
}

const CARD_FULL = { N: 'norte', NE: 'noreste', E: 'este', SE: 'sureste', S: 'sur', SO: 'suroeste', O: 'oeste', NO: 'noroeste' };
const cardWord = (abbr) => CARD_FULL[abbr] || abbr;

/* Mismos textos que STATUS y la primera línea de GUIDANCE de web/js/views/zona.js. */
const STATUS = {
  urgente: { label: 'Urgente', title: 'Puede haber fuego muy cerca de tu lugar' },
  aviso: { label: 'Calor cerca', title: 'Un satélite vio calor cerca' },
  riesgo: { label: 'Día peligroso', title: 'Hoy el clima es peligroso para incendios' },
  tranquilo: { label: 'Tranquilo', title: 'No se ve fuego cerca' },
};
const GUIDANCE_FIRST = {
  urgente: 'Si la autoridad ordena evacuar, sal de inmediato por la ruta que indiquen. No esperes a ver las llamas.',
  aviso: 'Revisa las noticias oficiales (SENAPRED, CONAF y tu municipio). El calor que ve un satélite puede ser un incendio, pero también una quema o una industria.',
  riesgo: 'Hoy no hagas quemas ni uses maquinaria que produzca chispas (esmeriles, soldadura, cortadoras) cerca de pasto seco.',
  tranquilo: 'Aprovecha para preparar tu casa: limpia techos y canaletas, poda y retira material seco alrededor.',
};
const ALERT_LEVEL = { urgente: 'Urgente', aviso: 'Aviso' };

const token = () => {
  try { return JSON.parse(localStorage.getItem('brasa:token')) || null; } catch { return null; }
};

class ApiFail extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function get(path) {
  let response;
  try {
    response = await fetch(path, { headers: { 'X-Brasa-Token': token() } });
  } catch {
    throw new ApiFail('Sin conexión con el servidor de BRASA.', 0);
  }
  if (response.status === 401) {
    // El servidor ya no reconoce este dispositivo (por ejemplo, base reiniciada).
    try { localStorage.removeItem('brasa:token'); } catch { /* sin almacenamiento */ }
    throw new ApiFail('Este dispositivo ya no está registrado.', 401);
  }
  if (!response.ok) throw new ApiFail(`Error ${response.status}`, response.status);
  return response.json();
}

function placeCard(place, summary) {
  const status = summary?.status && STATUS[summary.status] ? summary.status : 'tranquilo';
  const card = el('article', `card${summary ? ` st-${status}` : ''}`);
  const head = el('div', 'card-head');
  const title = el('div');
  title.append(el('h2', null, place.name));
  title.append(el('p', 'sub', `${place.comuna ? place.comuna.name : 'Fuera de una comuna conocida'} · aviso a ${fmtNum(place.radius_km)} km`));
  head.append(title);
  if (summary) head.append(el('span', `badge ${status === 'urgente' ? 'urgente' : `st-${status}`}`, STATUS[status].label));
  card.append(head);
  if (!summary) {
    card.append(el('p', 'guide muted', 'No se pudo cargar el estado de este lugar.'));
    return card;
  }
  card.append(el('p', 'guide', GUIDANCE_FIRST[status]));
  const near = (summary.nearby || []).filter((o) => o.inside_radius && o.reliable);
  if (near.length) {
    const n = near[0];
    card.append(el('p', 'near',
      `Calor a ${fmtNum(n.distance_km, n.distance_km < 3 ? 1 : 0)} km, hacia el ${cardWord(n.direction)} · ${ago(n.observed_at)}`));
  }
  card.append(el('p', 'asof', `Datos: ${ago(summary.data_as_of)}`));
  return card;
}

function alertItem(a) {
  const level = a.level === 'urgente' ? 'urgente' : 'aviso';
  const li = el('li', `st-${level}`);
  const head = el('div');
  head.append(el('span', 'lvl', ALERT_LEVEL[level]), ' ', el('b', 'small', a.title || 'Aviso de calor cerca'));
  const meta = [fmtDateTime(a.created_at), a.place?.name || 'tu lugar'];
  if (a.distance_km != null) meta.push(`a ${fmtNum(a.distance_km)} km`);
  li.append(head, el('div', 'tiny muted', meta.join(' · ')));
  return li;
}

function emptyState() {
  const box = el('div', 'empty');
  box.append(el('p', null, 'Abre BRASA y guarda tu lugar; aquí verás su estado.'));
  $('#lite-places').replaceChildren(box);
  $('#lite-alerts-sec').hidden = true;
}

function paint(places, summaries, alerts) {
  const host = $('#lite-places');
  if (!places.length) { emptyState(); return; }
  host.replaceChildren(...places.map((p, i) => placeCard(p, summaries[i])));
  const sec = $('#lite-alerts-sec');
  const list = $('#lite-alerts');
  if (alerts === null) {
    sec.hidden = false;
    list.replaceChildren(el('li', 'muted small', 'No se pudieron cargar los avisos.'));
  } else if (alerts.length) {
    sec.hidden = false;
    list.replaceChildren(...alerts.slice(0, 5).map(alertItem));
  } else {
    sec.hidden = false;
    list.replaceChildren(el('li', 'muted small', 'Todavía no te hemos avisado de nada.'));
  }
}

function statusMsg(text, retry = false) {
  const box = $('#lite-status');
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

async function load() {
  if (!token()) {
    statusMsg('');
    emptyState();
    return;
  }
  statusMsg('Cargando…');
  let places;
  try {
    const [{ places: list }, inbox] = await Promise.all([
      get('/api/places'),
      get('/api/alerts?limit=5').catch(() => null),
    ]);
    places = list || [];
    const summaries = await Promise.all((places).map((p) => get(`/api/places/${p.id}/summary`).catch(() => null)));
    statusMsg('');
    paint(places, summaries, inbox?.alerts ?? null);
  } catch (err) {
    if (err.status === 401) { statusMsg(''); emptyState(); return; }
    statusMsg(`No se pudo cargar. ${err.message}`, true);
  }
}

load();
