/* Moderación de reportes ciudadanos. El token vive solo en la sesión del navegador. */
import { api, request } from './api.js';
import { utcDate } from './formato.js';
import { $, $$, ago, fmtDateTime, fmtNum, haversineKm, html, minutesSince, SENSOR_LABEL, toast } from './util.js';

// `typeof` porque node --test importa este módulo sin DOM (ver tests/js/admin.test.mjs).
let token = typeof sessionStorage === 'undefined' ? '' : sessionStorage.getItem('brasa:admin') || '';
let status = 'no_verificado';
let queue = [];
let comunaFilter = '';
// Incidentes abiertos de las últimas 48 h, para la línea de distancia de cada tarjeta
// (MOD-03): null cuando la consulta falló y entonces la línea no se muestra.
let incidentesCola = null;
// El desplegable se alimenta solo de respuestas sin filtrar: si se llenara con la lista
// filtrada, elegir una comuna vaciaría las demás opciones.
const knownComunas = new Map();
const ACTION_LABEL = { verificado: 'Verificó', descartado: 'Descartó', no_verificado: 'Devolvió a revisión' };

async function call(path, init = {}) {
  const response = await fetch(path, { ...init, headers: { ...(init.headers || {}), 'X-Admin-Token': token, 'Content-Type': 'application/json' } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Error ${response.status}`);
  return body;
}

// Las fotos llegan como blob (requieren el token); se liberan al recargar la cola.
let photoUrls = [];
async function photoUrl(id) {
  const response = await fetch(`/api/reports/${id}/photo`, { headers: { 'X-Admin-Token': token } });
  if (!response.ok) return null;
  const url = URL.createObjectURL(await response.blob());
  photoUrls.push(url);
  return url;
}
function releasePhotos() { photoUrls.forEach((u) => URL.revokeObjectURL(u)); photoUrls = []; }

async function enter() {
  let me;
  try { me = await call('/api/admin/me'); } catch (err) {
    toast(err.message, 'error'); $('#panel').hidden = true; $('#login').hidden = false; return;
  }
  $('#login').hidden = true;
  $('#panel').hidden = false;
  // Dar de alta o revocar moderadores es solo del token maestro.
  $('[data-tab="team"]').hidden = !me.superuser;
  showTab('reports');
}

function showTab(name) {
  $$('[data-tab]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tab === name)));
  $('#queue').hidden = name !== 'reports';
  $('#log').hidden = name !== 'log';
  $('#team').hidden = name !== 'team';
  $('#salud').hidden = name !== 'salud';
  if (name === 'reports') load();
  else if (name === 'log') loadLog();
  else if (name === 'team') loadTeam();
  else loadSalud();
}

async function load() {
  let data;
  // El filtro va al servidor: la cola llega cortada a los 200 más viejos y un reporte
  // de la comuna elegida que quede fuera del corte no existiría para el cliente.
  const query = comunaFilter ? `&comuna=${encodeURIComponent(comunaFilter)}` : '';
  // Una sola consulta de incidentes por carga (MOD-03); si falla, las tarjetas se
  // pintan igual, solo sin la línea de distancia.
  try {
    [data, incidentesCola] = await Promise.all([
      call(`/api/admin/reports?status=${status}${query}`),
      api.incidents(48).then((d) => (Array.isArray(d?.incidents) ? d.incidents : null)).catch(() => null),
    ]);
  } catch (err) {
    toast(err.message, 'error'); $('#panel').hidden = true; $('#login').hidden = false; return;
  }
  releasePhotos();
  queue = data.reports;
  if (!comunaFilter) {
    knownComunas.clear();
    queue.forEach((r) => { if (r.comuna_code) knownComunas.set(String(r.comuna_code), r.comuna || `Código ${r.comuna_code}`); });
  }
  const select = $('#comuna');
  select.innerHTML = '<option value="">Todas las comunas</option>' +
    [...knownComunas.entries()].sort((a, b) => a[1].localeCompare(b[1], 'es'))
      .map(([code, name]) => String(html`<option value="${code}">${name}</option>`)).join('');
  select.value = knownComunas.has(comunaFilter) ? comunaFilter : '';
  comunaFilter = select.value;
  render();
}

/* Evidencia satelital junto al reporte (la misma que el formulario pide contrastar): una
 * consulta a /api/observations por tarjeta, con la caja del radio de contraste. `evidenciaCerca`
 * es pura para probarla con node --test; tiene tres estados honestos: detecciones,
 * sin detecciones (con la ventana explícita) y «no se pudo consultar»; nunca «no hay fuego». */
const EVIDENCIA_KM = 10;
const EVIDENCIA_HORAS = 6;
const EVIDENCIA_MAX = 24; // tope de tarjetas con consulta por render; el resto queda sin chip

export function evidenciaCerca(reporte, puntos, { km = EVIDENCIA_KM, horas = EVIDENCIA_HORAS, ahora = Date.now() } = {}) {
  if (!Array.isArray(puntos)) return { n: 0, cerca: [], texto: 'No se pudo consultar la evidencia satelital', estado: 'error' };
  if (!Number.isFinite(reporte?.lat) || !Number.isFinite(reporte?.lon)) {
    return { n: 0, cerca: [], texto: 'El reporte no tiene coordenadas para contrastar', estado: 'error' };
  }
  const dist = (d) => (d < 1 ? `${fmtNum(Math.round(d * 1000))} m` : `${fmtNum(d, d < 10 ? 1 : 0)} km`);
  const ordenados = puntos
    .filter((p) => p && Number.isFinite(p.lat) && Number.isFinite(p.lon))
    .map((p) => ({ km: haversineKm(reporte.lat, reporte.lon, p.lat, p.lon), p }))
    .filter((x) => x.km <= km)
    .sort((a, b) => a.km - b.km);
  const cerca = ordenados.map(({ km: d, p }) => ({
    km: d,
    minutos: Math.round(minutesSince(p.observed_at, ahora)),
    sensor: SENSOR_LABEL[p.sensor]?.split(' ')[0] || p.sensor || 'satélite',
  }));
  if (!cerca.length) {
    return { n: 0, cerca, texto: `Sin detecciones a menos de ${fmtNum(km)} km en las últimas ${horas} h`, estado: 'sin_detecciones' };
  }
  const masCercana = ordenados[0];
  const texto = cerca.length === 1
    ? `1 detección a ${dist(masCercana.km)} · ${ago(masCercana.p.observed_at, ahora)} (${cerca[0].sensor})`
    : `${cerca.length} detecciones, la más cercana a ${dist(masCercana.km)}`;
  return { n: cerca.length, cerca, texto, estado: 'detecciones' };
}

// Caja del radio de contraste: 10 km ≈ ±0,09° en latitud; en longitud se corrige con el coseno.
function bboxAlrededor(lat, lon, km) {
  const dLat = km / 110.574;
  const dLon = km / (111.32 * Math.cos((lat * Math.PI) / 180));
  return `${lon - dLon},${lat - dLat},${lon + dLon},${lat + dLat}`;
}

// La tarjeta se pinta primero y el chip se rellena al responder: si la consulta falla
// o tarda, el moderador no queda esperando.
async function cargarEvidencia(r, slot) {
  if (!slot) return;
  let puntos = null;
  if (Number.isFinite(r.lat) && Number.isFinite(r.lon)) {
    try {
      const res = await fetch(`/api/observations?bbox=${bboxAlrededor(r.lat, r.lon, EVIDENCIA_KM)}&hours=${EVIDENCIA_HORAS}`);
      puntos = (await res.json()).points;
    } catch { /* puntos queda null: evidenciaCerca devuelve el estado de error */ }
  }
  slot.textContent = evidenciaCerca(r, puntos, { km: EVIDENCIA_KM, horas: EVIDENCIA_HORAS }).texto;
}

/* Distancia al incidente más cercano (MOD-03): quien modera ve en la tarjeta si el aviso
 * está a 40 km de cualquier fuego o si corrobora un incendio real. `cercaDe` es pura para
 * probarla con node --test; el umbral es el centro de la huella, no un perímetro oficial. */
const CERCA_KM = 20;
export function cercaDe(reporte, incidents) {
  if (!Number.isFinite(reporte?.lat) || !Number.isFinite(reporte?.lon)) return null;
  const lista = Array.isArray(incidents) ? incidents : incidents?.incidents;
  if (!Array.isArray(lista)) return null;
  let mejor = null;
  for (const inc of lista) {
    if (!inc || !Number.isFinite(inc.lat) || !Number.isFinite(inc.lon)) continue;
    const km = haversineKm(reporte.lat, reporte.lon, inc.lat, inc.lon);
    if (km < CERCA_KM && (mejor === null || km < mejor.km)) mejor = { km, incident: inc };
  }
  return mejor ? { km: Math.round(mejor.km * 10) / 10, incident: mejor.incident } : null;
}

/** Texto de la tarjeta: distancia y contexto del incidente más cercano, o el aviso de
 *  «revisa si es una quema» cuando no hay ninguno dentro del umbral. Null cuando la
 *  consulta de incidentes no está disponible o al reporte le faltan coordenadas. */
export function cercaDeLinea(reporte, incidents, ahora = Date.now()) {
  if (!Array.isArray(incidents) || !Number.isFinite(reporte?.lat) || !Number.isFinite(reporte?.lon)) return null;
  const c = cercaDe(reporte, incidents);
  if (!c) return `Sin incendios a menos de ${fmtNum(CERCA_KM)} km: revisa si es una quema`;
  const inc = c.incident || {};
  const partes = [
    inc.status,
    Number.isFinite(inc.n_obs) ? `${fmtNum(inc.n_obs)} ${inc.n_obs === 1 ? 'foco' : 'focos'}` : null,
    inc.last_seen_at ? `última detección ${ago(inc.last_seen_at, ahora)}` : null,
  ].filter(Boolean);
  return `A ${fmtNum(c.km, 1)} km del incidente más cercano${partes.length ? ` (${partes.join(', ')})` : ''}`;
}

function render() {
  const items = $('#items');
  const shown = comunaFilter ? queue.filter((r) => String(r.comuna_code) === comunaFilter) : queue;
  $('#meta').textContent = shown.length
    ? `${shown.length} en cola · el más viejo lleva ${ago(shown[0].created_at).replace(/^hace /, '')}`
    : '';
  if (!shown.length) { items.innerHTML = '<p class="muted">No hay reportes en este estado.</p>'; return; }
  items.innerHTML = String(html`${shown.map((r) => {
    const cercania = incidentesCola ? cercaDeLinea(r, incidentesCola) : null;
    return html`<article class="card" data-id="${r.id}">
    ${r.has_photo ? html`<img alt="Foto del reporte" data-photo="${r.id}" />` : html`<div class="empty">Sin foto</div>`}
    <div class="card-title" style="margin-top:8px">${r.kind_label}</div>
    <div class="card-sub">${r.comuna || 'Sin comuna'} · ${fmtDateTime(r.created_at)} · ${ago(r.created_at)}</div>
    ${cercania ? html`<div class="tiny" style="margin-top:3px">${cercania}</div>` : ''}
    ${r.corroboraciones ? html`<div class="tiny" style="margin-top:4px"><b>${r.corroboraciones === 1 ? '1 vecino más lo corroboró' : `${r.corroboraciones} vecinos más lo corroboraron`}</b></div>` : ''}
    <p class="small" style="margin-top:6px">${r.description || 'Sin descripción.'}</p>
    <a class="tiny" href="https://www.openstreetmap.org/?mlat=${r.lat}&mlon=${r.lon}#map=14/${r.lat}/${r.lon}" target="_blank" rel="noopener">${r.lat.toFixed(4)}, ${r.lon.toFixed(4)} ↗</a>
    <div class="tiny" data-evidencia style="margin-top:4px"></div>
    <input class="input" placeholder="Nota (cómo se verificó)" data-note style="margin-top:8px" value="${r.moderator_note || ''}" />
    <div class="card-actions"><button class="btn btn-sm btn-primary" data-set="verificado">Verificar</button>
      <button class="btn btn-sm btn-danger" data-set="descartado">Descartar</button>
      ${r.status !== 'no_verificado' ? html`<button class="btn btn-sm btn-ghost" data-set="no_verificado">Volver a pendiente</button>` : ''}</div>
  </article>`;
  })}`);
  items.querySelectorAll('[data-photo]').forEach(async (img) => { const url = await photoUrl(img.dataset.photo); if (url) img.src = url; });
  const slots = items.querySelectorAll('[data-evidencia]');
  shown.slice(0, EVIDENCIA_MAX).forEach((r, i) => cargarEvidencia(r, slots[i]));
  items.querySelectorAll('[data-set]').forEach((b) => b.addEventListener('click', async () => {
    const card = b.closest('[data-id]');
    try {
      await call(`/api/admin/reports/${card.dataset.id}`, { method: 'POST', body: JSON.stringify({ status: b.dataset.set, note: card.querySelector('[data-note]').value }) });
      toast('Reporte actualizado.');
      load();
    } catch (err) { toast(err.message, 'error'); }
  }));
}

async function loadLog() {
  const items = $('#log-items');
  try {
    const { log } = await call('/api/admin/moderation-log');
    items.innerHTML = log.length ? String(html`${log.map((e) => html`<article class="card">
      <div class="card-title">${e.moderator} · ${ACTION_LABEL[e.action] || e.action}</div>
      <div class="card-sub">${fmtDateTime(e.created_at)} · ${ago(e.created_at)}</div>
      ${e.note ? html`<p class="small" style="margin-top:6px">${e.note}</p>` : ''}
      <div class="tiny muted" style="margin-top:6px">Reporte ${e.report_id.slice(0, 8)}</div>
    </article>`)}`) : '<p class="muted">Aún no hay decisiones registradas.</p>';
  } catch (err) { toast(err.message, 'error'); }
}

async function loadTeam() {
  const list = $('#mod-list');
  try {
    const { moderators } = await call('/api/admin/moderators');
    list.innerHTML = moderators.length ? String(html`${moderators.map((m) => html`<article class="card" data-mid="${m.id}">
      <div class="card-title">${m.name}</div>
      <div class="card-sub">${m.revoked_at ? `Acceso revocado ${ago(m.revoked_at)}` : `Activo desde ${fmtDateTime(m.created_at)}`}</div>
      ${m.revoked_at ? '' : html`<div class="card-actions"><button class="btn btn-sm btn-danger" data-revoke>Revocar acceso</button></div>`}
    </article>`)}`) : '<p class="muted">Aún no hay moderadores; crea el primero arriba.</p>';
    list.querySelectorAll('[data-revoke]').forEach((b) => b.addEventListener('click', () => revoke(b)));
  } catch (err) { toast(err.message, 'error'); }
}

// Revocar pide un segundo clic: no se deshace (para devolver el acceso hay que crear un token nuevo).
async function revoke(button) {
  if (button.dataset.confirm !== '1') {
    button.dataset.confirm = '1';
    button.textContent = 'Confirmar revocación';
    setTimeout(() => { button.dataset.confirm = ''; button.textContent = 'Revocar acceso'; }, 4000);
    return;
  }
  try {
    await call(`/api/admin/moderators/${button.closest('[data-mid]').dataset.mid}/revoke`, { method: 'POST' });
    toast('Acceso revocado.');
    loadTeam();
  } catch (err) { toast(err.message, 'error'); }
}

/* Pestaña Salud (OPS-29, que absorbe AUTO-09): el estado real del servicio en una sola
 * pantalla —frescura, fuentes, fallos de 24 h, huecos de GOES, cupos y respaldos— y por
 * cada problema un «qué revisar» concreto, sin abrir GitHub ni /api/status a mano.
 * `/api/status` es un GET público: se lee con `request()`, nunca por `call()` (que
 * adjuntaría X-Admin-Token). `saludResumen` es pura (sin DOM ni fetch) para probarla con
 * node --test; el pintado va solo con `textContent`, sin inyectar HTML del servidor. */
const OPERACION_URL = 'https://github.com/falopass/brasas/blob/main/docs/OPERACION.md';
const NIVEL_BADGE = { tranquilo: 'al día', aviso: 'revisar', urgente: 'problema', sin_dato: 'sin dato' };

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
};

/** Nivel de severidad: urgente si al menos uno lo es, aviso si alguno está para revisar,
 *  sin_dato solo si todos lo están; si no, tranquilo. */
const nivelDe = (...niveles) =>
  (niveles.includes('urgente') ? 'urgente' : niveles.includes('aviso') ? 'aviso'
    : niveles.every((n) => n === 'sin_dato') ? 'sin_dato' : 'tranquilo');

export function saludResumen(status = {}, incidents = {}) {
  const st = status && typeof status === 'object' ? status : {};
  const ciclo = st.last_cycle && typeof st.last_cycle === 'object' ? st.last_cycle : {};
  const frescura = st.freshness && typeof st.freshness === 'object' ? st.freshness : {};
  // La edad del respaldo se mide contra el reloj del servidor (time_utc), no el del
  // navegador: un reloj de cliente desfasado no debe inventar un respaldo atrasado.
  const ahora = utcDate(st.time_utc)?.getTime() ?? Date.now();
  const backupError = typeof ciclo.backup_error === 'string' ? ciclo.backup_error.trim() : '';
  const porProducto = st.failures_24h || st.errors?.by_product || {};
  const fuentes = Object.entries(porProducto)
    .filter(([, p]) => p && typeof p === 'object')
    .map(([producto, p]) => ({
      producto,
      runs: p?.runs ?? 0,
      failed: p?.failed ?? 0,
      last_failed_at: p?.last_failed_at ?? null,
      last_error: p?.last_error ?? null,
    }));
  const lista = Array.isArray(incidents?.incidents) ? incidents.incidents : null;
  // «Fuera de Chile» = sin comuna y sin official_ref: /api/incidents ya publica solo
  // territorio chileno (comuna o CONAF), así que un caso así es una regresión del backend.
  const afuera = (lista || []).filter((i) => i && i.comuna_code == null && i.official_ref == null);
  // Incendios oficiales de CONAF sin comuna emparejada: son chilenos, pero su riesgo y
  // sus avisos quedan sin calcular hasta asignarles una comuna por coordenadas.
  const sinComuna = (lista || []).filter((i) => i && i.comuna_code == null && i.official_ref != null);
  // Los *_error del ciclo llegan como nombres de clave; los del respaldo ya cuentan en su tarjeta.
  const errores = [
    ...(ciclo.error ? [String(ciclo.error)] : []),
    ...(Array.isArray(st.errors?.cycle_errors) ? st.errors.cycle_errors : []),
  ].filter((e) => e !== 'backup_error' && e !== 'restore_error');
  const respaldoMalo = ciclo.backup === false || Boolean(backupError) || Boolean(ciclo.restore_error);
  const metas = [];
  if (ciclo.backup === false) metas.push('db/brasa.db');
  // `work_backup: false` a secas no es falla: work.db se sube una vez por hora, no en cada
  // ciclo; solo cuenta cuando el error del respaldo lo menciona o coincide con su mensaje.
  if ((ciclo.work_backup === false && backupError) || /\bwork\b/i.test(backupError)) metas.push('db/work.db.gz');
  if (respaldoMalo && !metas.length) metas.push('db/brasa.db');
  const queHacerRespaldo = respaldoMalo
    ? `Revisar ${metas.map((m) => `/_internal/storage/${m}`).join(' y ')} en el Worker (error: ${backupError || ciclo.restore_error || 'sin mensaje'}).`
    : null;

  // Bloque `backup` publicado por /api/status: la copia diaria a R2 con su tamaño y su hora.
  // Si el bloque no viene, es «sin dato», no un respaldo fallido.
  const backup = st.backup && typeof st.backup === 'object' ? st.backup : null;
  const respaldoSinDato = backup != null && backup.bytes == null;
  const respaldoViejo = backup != null && backup.bytes != null && minutesSince(backup.updated_at, ahora) > 36 * 60;
  const respaldoProblema = respaldoMalo || respaldoSinDato || respaldoViejo;
  const queRevisarRespaldo = respaldoMalo ? queHacerRespaldo
    : respaldoSinDato && backup?.reason === 'sin_credenciales'
      ? 'El servidor no tiene credenciales de respaldo (R2): configurarlas o aceptar que este despliegue va sin copia.'
      : respaldoProblema ? 'Correr el respaldo a mano (POST /internal/backup) y revisar el issue de monitoreo.'
      : null;

  // `errors.desfase` lo escribe el servidor: distingue «la fuente no trae nada nuevo» de
  // «la ingesta está parada» y trae su propio «qué hacer».
  const desfase = st.errors?.desfase && typeof st.errors.desfase === 'object' ? st.errors.desfase : {};
  const desfaseMal = typeof desfase.estado === 'string' && desfase.estado !== 'al_dia';
  const sinMarca = !st.last_ingest_at && !frescura.last_ingest_at;
  const datosNivel = frescura.stale === true || ['sin_datos', 'reloj', 'parado'].includes(desfase.estado)
    ? 'urgente' : desfaseMal ? 'aviso' : sinMarca ? 'sin_dato' : 'tranquilo';
  const newestAt = Object.values(st.newest_observation || {}).filter(Boolean).sort().pop() ?? null;

  // Última corrida por producto (`runs`): «falló la última» se ve aunque las 24 h sumen una sola.
  const productos = (Array.isArray(st.runs) ? st.runs : [])
    .filter((r) => r && typeof r === 'object')
    .map((r) => ({
      producto: [r.provider, r.product].filter(Boolean).join(' · ') || 'producto',
      ok: r.ok === true,
      finished_at: r.finished_at ?? r.started_at ?? null,
      last_ok_at: r.last_ok_at ?? null,
      message: r.ok === true ? null : (typeof r.message === 'string' ? r.message : null),
    }));

  const detalle = st.errors?.cycle_detail && typeof st.errors.cycle_detail === 'object' ? st.errors.cycle_detail : {};
  const erroresCiclo = errores
    .map((clave) => ({ clave, detalle: typeof detalle[clave] === 'string' ? detalle[clave] : null }))
    .slice(0, 3);

  const goesMissing = Number(st.goes_missing);
  const goesGap = st.goes_gap === true || Number(st.goes_gap) > 0;
  const goesSinDato = !Array.isArray(st.goes_sweeps) || st.goes_sweeps.length === 0;
  const goes = {
    missing: Number.isFinite(goesMissing) ? goesMissing : 0,
    gap: goesGap,
    sweeps: (Array.isArray(st.goes_sweeps) ? st.goes_sweeps : [])
      .map((s) => ({ ok: s?.ok === true, started_at: s?.started_at ?? null })),
    sin_dato: goesSinDato,
    nivel: goesSinDato ? 'sin_dato' : goesGap ? 'urgente' : (Number.isFinite(goesMissing) && goesMissing > 0) ? 'aviso' : 'tranquilo',
  };

  // Cupo de la clave FIRMS en su ventana de 10 min: cerca del tope las corridas de
  // VIIRS/MODIS empiezan a fallar con 429. Sin lectura se dice «sin dato», nunca un número.
  const fq = st.firms_quota && typeof st.firms_quota === 'object' ? st.firms_quota : {};
  const fLimit = Number(fq.limit);
  const fUsed = Number(fq.used);
  const fOk = fq.error !== true && Number.isFinite(fLimit) && fLimit > 0 && Number.isFinite(fUsed);
  const firms = {
    configured: st.firms_configured === true,
    sin_dato: !fOk,
    used: fOk ? fUsed : null,
    limit: fOk ? fLimit : null,
    checked_at: fq.checked_at ?? null,
    pct: fOk ? Math.round((100 * fUsed) / fLimit) : null,
    nivel: !fOk ? 'sin_dato' : fUsed >= fLimit ? 'urgente' : fUsed >= 0.8 * fLimit ? 'aviso' : 'tranquilo',
  };
  // Cupo diario de Open-Meteo: `scheduled.total` es el acumulado durable del día y
  // `locations` el de este proceso; el gasto honesto es el mayor de los dos.
  const om = st.open_meteo && typeof st.open_meteo === 'object' ? st.open_meteo : {};
  const omCap = Number(om.daily_cap);
  const omTot = typeof om.scheduled === 'object' && om.scheduled !== null ? Number(om.scheduled.total) : Number(om.scheduled);
  const omOk = Number.isFinite(omCap) && omCap > 0 && Number.isFinite(Number(om.locations));
  const omUsed = omOk ? Math.max(Number(om.locations), Number.isFinite(omTot) ? omTot : 0) : null;
  const openMeteo = {
    sin_dato: !omOk,
    used: omUsed,
    cap: omOk ? omCap : null,
    pct: omOk ? Math.round((100 * omUsed) / omCap) : null,
    nivel: !omOk ? 'sin_dato' : omUsed >= omCap ? 'urgente' : omUsed >= 0.8 * omCap ? 'aviso' : 'tranquilo',
  };

  const problemas = (respaldoProblema ? 1 : 0) + (frescura.stale === true || desfaseMal ? 1 : 0)
    + fuentes.filter((f) => f.failed > 0).length + errores.length
    + (afuera.length ? 1 : 0) + (sinComuna.length ? 1 : 0)
    + (goes.nivel === 'urgente' ? 1 : 0)
    + (['urgente', 'aviso'].includes(firms.nivel) ? 1 : 0)
    + (['urgente', 'aviso'].includes(openMeteo.nivel) ? 1 : 0);
  return {
    problemas,
    estado: problemas === 0 ? 'al día' : `${problemas} ${problemas === 1 ? 'problema' : 'problemas'}`,
    datos: {
      nivel: datosNivel,
      stale: frescura.stale === true,
      last_ingest_at: st.last_ingest_at ?? frescura.last_ingest_at ?? null,
      newest_at: newestAt,
      desfase_texto: typeof desfase.texto === 'string' ? desfase.texto : null,
      que_revisar: datosNivel === 'tranquilo' || datosNivel === 'sin_dato' ? null
        : (typeof desfase.que_hacer === 'string' ? desfase.que_hacer : 'Correr la ingesta a mano y revisar el issue de monitoreo.'),
    },
    ciclo: {
      finished_at: ciclo.finished_at ?? null,
      last_ingest_at: st.last_ingest_at ?? frescura.last_ingest_at ?? null,
      stale: frescura.stale === true,
      backup: ciclo.backup ?? null,
      work_backup: ciclo.work_backup ?? null,
      backup_error: backupError || null,
      errores,
      que_hacer: queHacerRespaldo,
    },
    fuentes,
    productos,
    errores_ciclo: erroresCiclo,
    goes,
    cupos: { nivel: nivelDe(firms.nivel, openMeteo.nivel), firms, open_meteo: openMeteo },
    respaldo: {
      nivel: respaldoProblema ? 'urgente' : backup === null ? 'sin_dato' : 'tranquilo',
      publicado: backup !== null,
      sin_dato: respaldoSinDato,
      viejo: respaldoViejo,
      bytes: backup?.bytes ?? null,
      updated_at: backup?.updated_at ?? null,
      work_bytes: backup?.work_bytes ?? null,
      work_updated_at: backup?.work_updated_at ?? null,
      reason: typeof backup?.reason === 'string' ? backup.reason : null,
      backup_error: backupError || (typeof ciclo.restore_error === 'string' ? ciclo.restore_error : null),
      que_revisar: queRevisarRespaldo,
    },
    territorio: {
      fuera: afuera.length,
      sin_comuna: sinComuna.length,
      muestra: [...afuera, ...sinComuna].slice(0, 5).map((i) => ({ id: i.id, lat: i.lat, lon: i.lon, nombre: i.official_name ?? null })),
      sin_dato: lista === null,
      que_hacer: [
        afuera.length ? 'Puntos sin comuna ni fuente oficial: el servidor solo publica territorio chileno, así que es una regresión del filtro de /api/incidents; revisar la ingesta.' : '',
        sinComuna.length ? 'Incendios de CONAF sin comuna: emparejar la comuna por coordenadas para que se calculen su riesgo y sus avisos.' : '',
      ].filter(Boolean).join(' ') || null,
    },
  };
}

function territorioLinea(t) {
  const partes = [];
  if (t.fuera) partes.push(`${t.fuera} ${t.fuera === 1 ? 'punto fuera' : 'puntos fuera'} de Chile`);
  if (t.sin_comuna) partes.push(`${t.sin_comuna} ${t.sin_comuna === 1 ? 'incendio oficial' : 'incendios oficiales'} sin comuna`);
  return partes.length ? partes.join(' · ') : 'Todo dentro de Chile.';
}

// Pintado con DOM y textContent: el servidor no dicta marcado a esta pestaña.
function tarjetaSalud(titulo, nivel = 'tranquilo') {
  const card = el('article', 'card');
  const head = el('div', 'card-head');
  head.append(
    el('div', 'card-title', titulo),
    el('span', `status-badge${nivel === 'sin_dato' ? '' : ` st-${nivel}`}`, NIVEL_BADGE[nivel] || nivel));
  card.append(head);
  return card;
}
function linea(card, texto, cls = 'small') {
  const p = el('p', cls, texto);
  p.style.marginTop = '6px';
  card.append(p);
  return p;
}
function queRevisar(card, texto) {
  const p = linea(card, '', 'small');
  const a = el('a', null, 'docs/OPERACION.md');
  a.href = OPERACION_URL;
  a.target = '_blank';
  a.rel = 'noopener';
  p.append(el('b', null, 'Qué revisar:'), ` ${texto} `, a, '.');
  return p;
}

function cardDatos(d) {
  const card = tarjetaSalud('Datos y frescura', d.nivel);
  const p = linea(card, d.last_ingest_at
    ? `Última ingesta ${fmtDateTime(d.last_ingest_at)} · ${ago(d.last_ingest_at)}${d.stale ? ' · dato viejo' : ''}`
    : 'Sin marca de la última ingesta.');
  if (d.stale) p.style.color = 'var(--danger)';
  if (d.newest_at) linea(card, `Detección más nueva ${ago(d.newest_at)}`, 'tiny muted');
  if (d.desfase_texto) linea(card, d.desfase_texto, 'tiny muted');
  if (d.que_revisar) queRevisar(card, d.que_revisar);
  return card;
}

function cardFuentes(productos) {
  const nivel = productos.length ? nivelDe(...productos.map((p) => (p.ok ? 'tranquilo' : 'urgente'))) : 'sin_dato';
  const card = tarjetaSalud('Fuentes', nivel);
  if (!productos.length) linea(card, 'Sin corridas registradas todavía.', 'small muted');
  for (const p of productos) {
    const l = linea(card, `${p.producto}: ${p.ok ? 'correcta' : 'falló'} ${ago(p.finished_at)} · último éxito ${p.last_ok_at ? ago(p.last_ok_at) : 'sin datos'}`);
    if (!p.ok) l.style.color = 'var(--danger)';
    if (p.message) linea(card, p.message, 'tiny muted');
  }
  if (nivel === 'urgente') queRevisar(card, 'reintentar la fuente en el próximo ciclo; si un producto falla dos veces seguidas, mirar /api/status?history=1.');
  return card;
}

function cardFallos(r) {
  const malas = r.fuentes.filter((f) => f.failed > 0);
  const nivel = malas.length || r.errores_ciclo.length ? 'urgente' : 'tranquilo';
  const card = tarjetaSalud('Fallos en 24 h', nivel);
  if (!malas.length && !r.errores_ciclo.length) linea(card, 'Sin fallos en las últimas 24 h.', 'small muted');
  for (const f of malas) {
    const l = linea(card, `${f.producto}: ${f.failed} de ${f.runs} corridas fallidas${f.last_failed_at ? ` · última ${ago(f.last_failed_at)}` : ''}`);
    l.style.color = 'var(--danger)';
    if (f.last_error) linea(card, f.last_error, 'tiny muted');
  }
  for (const e of r.errores_ciclo) {
    linea(card, `También falló: ${e.clave}${e.detalle ? ` · ${e.detalle}` : ''}`, 'tiny');
  }
  if (nivel === 'urgente') queRevisar(card, 'reintentar la fuente en el próximo ciclo y revisar el último issue que abrió el monitoreo.');
  return card;
}

function cardGoes(g) {
  const card = tarjetaSalud('GOES-19', g.nivel);
  if (g.sin_dato) linea(card, 'Sin barridos registrados.', 'small muted');
  else {
    const p = linea(card, g.missing ? `En la última hora faltan ${fmtNum(g.missing)} de 6 barridos.` : 'En la última hora no falta ningún barrido.');
    if (g.gap) p.style.color = 'var(--danger)';
    for (const s of g.sweeps) linea(card, `${s.ok ? 'Barrido recibido' : 'Barrido falló'} ${ago(s.started_at)}`, 'tiny muted');
  }
  if (g.gap) queRevisar(card, 'correr la ingesta a mano y revisar el issue de monitoreo: GOES-19 entrega un barrido cada 10 minutos.');
  return card;
}

function cardCupos(c) {
  const card = tarjetaSalud('Cupos', c.nivel);
  const f = c.firms;
  if (!f.configured) linea(card, 'FIRMS: sin clave configurada; VIIRS y MODIS no se ingieren.', 'small muted');
  else if (f.sin_dato) linea(card, 'FIRMS: sin dato del cupo (la última consulta falló o aún no hay lectura; se reintenta cada 45 min).', 'small muted');
  else {
    const p = linea(card, `FIRMS: ${fmtNum(f.used)} de ${fmtNum(f.limit)} transacciones en la ventana de 10 min (${fmtNum(f.pct)} %), consultado ${ago(f.checked_at)}.`);
    if (f.nivel !== 'tranquilo') p.style.color = 'var(--danger)';
  }
  const o = c.open_meteo;
  if (o.sin_dato) linea(card, 'Open-Meteo: sin dato del cupo diario.', 'small muted');
  else {
    const p = linea(card, `Open-Meteo: ${fmtNum(o.used)} de ${fmtNum(o.cap)} ubicaciones hoy (${fmtNum(o.pct)} %).`);
    if (o.nivel !== 'tranquilo') p.style.color = 'var(--danger)';
  }
  if (c.nivel === 'urgente' || c.nivel === 'aviso') {
    queRevisar(card, 'el cupo de FIRMS se renueva solo cada 10 min y el de Open-Meteo a medianoche; si se agotan, las corridas fallan con 429 y el mapa de peligro queda congelado.');
  }
  return card;
}

function cardRespaldo(r) {
  const card = tarjetaSalud('Respaldo', r.nivel);
  if (!r.publicado) linea(card, 'El servidor no publica el estado del respaldo.', 'small muted');
  else {
    const p = linea(card, r.bytes != null
      ? `Base: ${fmtNum(r.bytes)} bytes · ${ago(r.updated_at)}${r.viejo ? ' · atrasado' : ''}`
      : 'Sin respaldo publicado.');
    if (r.nivel === 'urgente') p.style.color = 'var(--danger)';
    if (r.work_bytes != null) linea(card, `Datos de trabajo: ${fmtNum(r.work_bytes)} bytes · ${ago(r.work_updated_at)}`, 'tiny muted');
    if (r.reason === 'sin_credenciales') linea(card, 'El servidor no tiene credenciales de respaldo (R2).', 'tiny muted');
  }
  if (r.backup_error) { const e = linea(card, r.backup_error, 'tiny'); e.style.color = 'var(--danger)'; }
  if (r.que_revisar) queRevisar(card, r.que_revisar);
  return card;
}

function cardTerritorio(t) {
  const nivel = t.sin_dato ? 'sin_dato' : t.fuera || t.sin_comuna ? 'urgente' : 'tranquilo';
  const card = tarjetaSalud('Territorio', nivel);
  if (t.sin_dato) linea(card, 'No se pudo consultar /api/incidents.', 'small muted');
  else {
    const p = linea(card, territorioLinea(t));
    if (nivel === 'urgente') p.style.color = 'var(--danger)';
    for (const i of t.muestra) linea(card, `${i.id}${i.nombre ? ` · ${i.nombre}` : ''} · ${i.lat}, ${i.lon}`, 'tiny muted');
    if (t.que_hacer) queRevisar(card, t.que_hacer);
  }
  return card;
}

async function loadSalud() {
  const items = $('#salud-items');
  const carga = el('p', 'muted', 'Consultando el estado…');
  carga.setAttribute('role', 'status');
  carga.style.marginTop = '12px';
  items.replaceChildren(carga);
  try {
    // GET público, sin X-Admin-Token: el estado de las fuentes no es un dato de moderación.
    const [statusData, incidentsData] = await Promise.all([
      request('/api/status'),
      api.incidents(48).catch(() => null),
    ]);
    const t = statusData?.time_utc;
    $('#salud-ultima').textContent = `Última consulta ${t ? `${ago(t)} · ${fmtDateTime(t)}` : 'recién'}`;
    renderSalud(saludResumen(statusData, incidentsData));
  } catch (err) {
    toast(err.message, 'error');
    const box = el('div', 'callout callout-warn');
    box.setAttribute('role', 'alert');
    box.append(el('b', null, `No se pudo leer el estado del servicio: ${err.message}`));
    const row = el('div', 'btn-row');
    row.style.marginTop = '10px';
    const btn = el('button', 'btn btn-sm', 'Reintentar');
    btn.type = 'button';
    btn.addEventListener('click', loadSalud);
    row.append(btn);
    box.append(row);
    items.replaceChildren(box);
  }
}

function renderSalud(r) {
  $('#salud-estado').textContent = r.problemas ? `${r.estado} por mirar.` : 'Todo al día.';
  $('#salud-items').replaceChildren(
    cardDatos(r.datos), cardFuentes(r.productos), cardFallos(r), cardGoes(r.goes),
    cardCupos(r.cupos), cardRespaldo(r.respaldo), cardTerritorio(r.territorio));
}

// Los listeners y el arranque solo corren en el navegador; node --test importa el módulo sin DOM.
if (typeof document !== 'undefined') {
$('#login').addEventListener('submit', (e) => {
  e.preventDefault();
  token = $('#token').value.trim();
  sessionStorage.setItem('brasa:admin', token);
  enter();
});
$('#new-mod').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const created = await call('/api/admin/moderators', { method: 'POST', body: JSON.stringify({ name: $('#mod-name').value }) });
    $('#mod-token-value').value = created.token;
    $('#mod-token').hidden = false;
    $('#mod-name').value = '';
    toast(`Token de ${created.name} listo: cópialo ahora, no se vuelve a mostrar.`);
    loadTeam();
  } catch (err) { toast(err.message, 'error'); }
});
$('#copy-token').addEventListener('click', async () => {
  const field = $('#mod-token-value');
  field.select();
  try { await navigator.clipboard.writeText(field.value); toast('Token copiado.'); }
  catch { toast('No se pudo copiar: selecciona el texto y cópialo a mano.', 'error'); }
});
$$('[data-tab]').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));
$('#salud [data-refresh]').addEventListener('click', loadSalud);
$('#comuna').addEventListener('change', () => { comunaFilter = $('#comuna').value; load(); });
document.querySelectorAll('[data-status]').forEach((b) => b.addEventListener('click', () => {
  status = b.dataset.status;
  document.querySelectorAll('[data-status]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  load();
}));
if (token) enter();
}
