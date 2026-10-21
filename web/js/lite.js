/* BRASA · modo liviano (web/lite.html): página mínima sin mapa para celulares de gama baja y
 * señal lenta. Sin dependencias ni vistas de la app: lee el token del dispositivo
 * (localStorage «brasa:token») y reusa la API. Es de solo lectura: sin token muestra el
 * estado vacío y no llama a la API ni crea suscriptores nuevos. */

import { ago, fmtDateTime, fmtNum, fmtTime, parseUTC } from './formato.js';

const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const tel = (n) => { const a = el('a', null, n); a.href = `tel:${n}`; return a; };

/* Tema: la preferencia guardada en la app (por defecto, oscuro como el resto de BRASA). */
try {
  const saved = JSON.parse(localStorage.getItem('brasa:theme'));
  document.documentElement.dataset.theme = saved || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
} catch { document.documentElement.dataset.theme = 'dark'; }

const minutesSince = (iso, now = Date.now()) => (iso ? (now - parseUTC(iso).getTime()) / 60000 : Infinity);
/* Umbral de frescura: lo manda /api/status (`freshness.stale_after_s`); 30 min solo si falta. */
let STALE_MIN = 30;

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
const RISK_LEVEL = { bajo: 'Bajo', moderado: 'Moderado', alto: 'Alto', extremo: 'Extremo' };

/* Voz alta y compartir por tarjeta (UX-02). Sin botones muertos: «Escuchar» solo se crea
   cuando hay speechSynthesis; «Compartir» baja al portapapeles y, en último caso, muestra
   el texto en #lite-status para copiarlo a mano. */
const synth = 'speechSynthesis' in window ? window.speechSynthesis : null;
let speakingBtn = null;

/* Tarjetas por lugar: {place, summary, state, node}. Cada una se repinta sola
   cuando llega su resumen o al reintentarla, sin esperar ni tocar a las demás (LIT-01). */
let cards = [];
let staleEl = null;
let loading = false;

function setSpeaking(btn, on) {
  btn.classList.toggle('speaking', on);
  btn.textContent = on ? 'Detener' : 'Escuchar';
}

function speak(text, btn) {
  if (speakingBtn === btn) {
    speakingBtn = null;
    setSpeaking(btn, false);
    synth.cancel();
    return;
  }
  if (speakingBtn) setSpeaking(speakingBtn, false);
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'es-CL';
  const voices = synth.getVoices?.() || [];
  u.voice = voices.find((v) => v.lang === 'es-CL')
    || voices.find((v) => v.lang === 'es-419')
    || voices.find((v) => (v.lang || '').toLowerCase().startsWith('es'))
    || null;
  speakingBtn = btn;
  setSpeaking(btn, true);
  u.onend = u.onerror = () => {
    if (speakingBtn === btn) { speakingBtn = null; setSpeaking(btn, false); }
  };
  synth.speak(u);
}

async function shareCard(text, title) {
  const url = `${location.origin}/web/lite.html`;
  if (navigator.share) {
    try { await navigator.share({ title, text: `${text}\n${url}`, url }); } catch { /* quien comparte canceló */ }
    return;
  }
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(`${text}\n${url}`);
      statusMsg('Copiado. Pégalo en WhatsApp o donde lo quieras enviar.');
      return;
    } catch { /* abajo se muestra el texto para copiarlo a mano */ }
  }
  statusMsg(`Copia y envía: ${text} ${url}`);
}

function speakBtn(aria, text) {
  const b = el('button', 'card-btn', 'Escuchar');
  b.type = 'button';
  b.setAttribute('aria-label', aria);
  b.addEventListener('click', () => speak(text, b));
  return b;
}

function cardActions(place, status, guide) {
  const row = el('div', 'card-actions');
  if (synth) {
    row.append(speakBtn(`Escuchar el estado de ${place.name}`,
      `${place.name}. ${STATUS[status].title}. ${guide}`));
  }
  const b = el('button', 'card-btn', 'Compartir');
  b.type = 'button';
  b.setAttribute('aria-label', `Compartir el estado de ${place.name}`);
  b.addEventListener('click', () => shareCard(
    `${place.name}: ${STATUS[status].label}. ${STATUS[status].title}.\n${guide}\nNo es una alerta oficial: sigue a SENAPRED.`,
    `BRASA · ${place.name}`));
  row.append(b);
  return row;
}

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

function placeCard(entry) {
  const { place, summary } = entry;
  const status = summary?.status && STATUS[summary.status] ? summary.status : 'tranquilo';
  const card = el('article', `card${summary ? ` st-${status}` : ''}`);
  const head = el('div', 'card-head');
  const title = el('div');
  title.append(el('h2', null, place.name));
  title.append(el('p', 'sub', `${place.comuna ? place.comuna.name : 'Fuera de una comuna conocida'} · aviso a ${fmtNum(place.radius_km)} km`));
  head.append(title);
  if (summary) head.append(el('span', `badge ${status === 'urgente' ? 'urgente' : `st-${status}`}`, STATUS[status].label));
  card.append(head);
  if (entry.state === 'loading') {
    const wait = el('p', 'guide muted', 'Consultando el estado…');
    wait.setAttribute('role', 'status');
    card.append(wait);
    return card;
  }
  if (!summary) {
    card.append(el('p', 'guide muted', 'No se pudo cargar el estado de este lugar.'));
    const row = el('div', 'card-actions');
    if (synth) {
      row.append(speakBtn(`Escuchar el estado de ${place.name}`,
        `${place.name}. No se pudo cargar el estado de este lugar.`));
    }
    const retry = el('button', 'card-btn', 'Reintentar');
    retry.type = 'button';
    retry.setAttribute('aria-label', `Reintentar la consulta del estado de ${place.name}`);
    retry.addEventListener('click', () => loadSummary(entry));
    row.append(retry);
    card.append(row);
    return card;
  }
  // Primero la fuente oficial: si CONAF informa un incendio dentro del radio, eso define el estado
  // (build_summary lo sube a aviso/urgente aunque no haya calor satelital confiable).
  const official = (summary.official || []).find((f) => f.inside_radius && f.status !== 'extinguido');
  if (official) {
    card.append(el('p', 'near',
      `CONAF informa un incendio a ${fmtNum(official.distance_km, official.distance_km < 3 ? 1 : 0)} km de este lugar, hacia el ${cardWord(official.direction)}${official.name ? ` · «${official.name}»` : ''}`));
  }
  const guide = official && status === 'aviso'
    ? 'CONAF ya informa un incendio cerca: revisa las noticias oficiales (SENAPRED, CONAF y tu municipio) y mantente atento.'
    : GUIDANCE_FIRST[status];
  card.append(el('p', 'guide', guide));
  // El clima del día ya viene en risk_days[0]; el color solo acompaña al texto del nivel.
  const today = (summary.risk_days || [])[0];
  const clima = el('p', `clima lv-${today && RISK_LEVEL[today.level] ? today.level : 'none'}`);
  clima.append(el('b', null, `Clima de hoy: ${RISK_LEVEL[today?.level] || 'sin dato'}`));
  if (today?.boton_rojo_hours != null) clima.append(' · CONAF: Botón Rojo');
  card.append(clima);
  // Mañana solo si hay dato (risk_days[1]); nunca una línea inventada.
  const tomorrow = (summary.risk_days || [])[1];
  if (tomorrow) {
    const manana = el('p', `clima lv-${RISK_LEVEL[tomorrow.level] ? tomorrow.level : 'none'}`);
    manana.append(el('b', null, `Mañana: ${RISK_LEVEL[tomorrow.level] || 'sin dato'}`));
    card.append(manana);
  }
  // Avisos vigentes de la DMC para la comuna (viento y calor extremo). Fuente oficial, nunca urgencia BRASA.
  const dmc = summary.dmc_alerts || [];
  if (dmc.length) {
    const line = el('p', 'near');
    line.setAttribute('role', 'status');
    line.append(el('b', null, [...new Set(dmc.map((a) => a.label))].join(' y ')),
      ` de la DMC${dmc[0].expires ? ` hasta ${fmtDateTime(dmc[0].expires)}` : ''} · `);
    const url = dmc[0].web || summary.dmc_source?.url;
    if (url) {
      const a = el('a', null, 'aviso oficial');
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener';
      line.append(a);
    }
    card.append(line);
  }
  if (!official) {
    const near = (summary.nearby || []).filter((o) => o.inside_radius && o.reliable);
    if (near.length) {
      const n = near[0];
      card.append(el('p', 'near',
        `Calor a ${fmtNum(n.distance_km, n.distance_km < 3 ? 1 : 0)} km, hacia el ${cardWord(n.direction)} · ${ago(n.observed_at)}`));
    }
  }
  card.append(el('p', 'asof', summary.data_as_of
    ? `Datos: ${ago(summary.data_as_of)} (${fmtTime(summary.data_as_of)}, hora de Chile)`
    : 'Datos: sin dato de actualización'));
  card.append(cardActions(place, status, guide));
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
  cards = [];
  staleEl = null;
  $('#lite-places').replaceChildren(box);
  $('#lite-alerts-sec').hidden = true;
}

function renderCard(entry) {
  const next = placeCard(entry);
  // Si la tarjeta que se reemplaza estaba hablando, el botón «Detener» no queda huérfano.
  if (synth && speakingBtn && entry.node?.contains(speakingBtn)) { synth.cancel(); speakingBtn = null; }
  entry.node.replaceWith(next);
  entry.node = next;
}

function paintCards() {
  if (synth) { synth.cancel(); speakingBtn = null; } // un repintado deja el botón «Detener» huérfano
  staleEl = null;
  for (const c of cards) c.node = placeCard(c);
  $('#lite-places').replaceChildren(...cards.map((c) => c.node));
}

/* Mismo aviso que zona.js: con datos atrasados, «no se ve fuego» no significa «no hay fuego».
   Se recalcula al llegar cada resumen; mientras haya tarjetas consultando la frescura del
   conjunto todavía no se sabe. */
function updateStaleNote() {
  staleEl?.remove();
  staleEl = null;
  if (cards.some((c) => c.state === 'loading')) return;
  const lastIngest = cards.map((c) => c.summary?.data_as_of).filter(Boolean).sort().pop();
  if (minutesSince(lastIngest) <= STALE_MIN) return;
  const note = el('div', 'stale-note');
  note.setAttribute('role', 'alert');
  note.append(el('b', null, lastIngest
    ? `Los datos de los satélites no se actualizan desde ${ago(lastIngest)}.`
    : 'BRASA no está recibiendo datos de los satélites.'),
    ' Que BRASA no muestre fuego no significa que no lo haya. Si ves humo o llamas, llama al ',
    tel('132'), ' o al ', tel('130'), '.');
  if (synth) {
    const row = el('div', 'card-actions');
    row.append(speakBtn('Escuchar el aviso de datos atrasados', note.textContent));
    note.append(row);
  }
  $('#lite-places').prepend(note);
  staleEl = note;
}

function paintAlerts(alerts) {
  const sec = $('#lite-alerts-sec');
  const list = $('#lite-alerts');
  sec.hidden = false;
  if (alerts === null) {
    list.replaceChildren(el('li', 'muted small', 'No se pudieron cargar los avisos.'));
  } else if (alerts.length) {
    list.replaceChildren(...alerts.slice(0, 5).map(alertItem));
  } else {
    list.replaceChildren(el('li', 'muted small', 'Todavía no te hemos avisado de nada.'));
  }
}

/* Pide el resumen de un solo lugar y repinta su tarjeta. La usa la carga inicial
   y el «Reintentar» de una tarjeta que falló. */
async function loadSummary(entry) {
  entry.state = 'loading';
  entry.summary = null;
  renderCard(entry);
  try {
    entry.summary = await get(`/api/places/${entry.place.id}/summary`);
    entry.state = 'ok';
  } catch {
    entry.state = 'error';
  }
  renderCard(entry);
  updateStaleNote();
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
    return true;
  }
  if (loading) return true;
  loading = true;
  if (refreshBtn) refreshBtn.disabled = true;
  statusMsg('Cargando…');
  try {
    // Avisos y estado del servicio van en paralelo y se pintan al llegar:
    // ninguno bloquea la primera tarjeta.
    const alertsP = get('/api/alerts?limit=5')
      .then((inbox) => paintAlerts(inbox?.alerts ?? null))
      .catch(() => paintAlerts(null));
    get('/api/status')
      .then((status) => { if (status?.freshness?.stale_after_s > 0) STALE_MIN = status.freshness.stale_after_s / 60; })
      .catch(() => null);
    const { places: list } = await get('/api/places');
    statusMsg('');
    const places = list || [];
    if (!places.length) { emptyState(); return true; }
    // Primera fase: el nombre de cada lugar aparece de inmediato, con «Consultando…».
    cards = places.map((place) => ({ place, summary: null, state: 'loading', node: null }));
    paintCards();
    // Segunda fase: cada tarjeta se repinta a medida que responde su resumen.
    cards.forEach(loadSummary);
    await alertsP;
    return true;
  } catch (err) {
    if (err.status === 401) { statusMsg(''); emptyState(); return true; }
    statusMsg(`No se pudo cargar. ${err.message}`, true);
    return false;
  } finally {
    loading = false;
    if (refreshBtn) refreshBtn.disabled = false;
  }
}

const refreshBtn = $('#lite-refresh');
if (refreshBtn) {
  refreshBtn.addEventListener('click', async () => {
    if (await load()) statusMsg('Actualizado.');
  });
}
load();
