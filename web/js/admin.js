/* Moderación de reportes ciudadanos. El token vive solo en la sesión del navegador. */
import { $, $$, ago, fmtDateTime, html, toast } from './util.js';

// `typeof` porque node --test importa este módulo sin DOM (ver tests/js/admin.test.mjs).
let token = typeof sessionStorage === 'undefined' ? '' : sessionStorage.getItem('brasa:admin') || '';
let status = 'no_verificado';
let queue = [];
let comunaFilter = '';
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
  try { data = await call(`/api/admin/reports?status=${status}${query}`); } catch (err) {
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

function render() {
  const items = $('#items');
  const shown = comunaFilter ? queue.filter((r) => String(r.comuna_code) === comunaFilter) : queue;
  $('#meta').textContent = shown.length
    ? `${shown.length} en cola · el más viejo lleva ${ago(shown[0].created_at).replace(/^hace /, '')}`
    : '';
  if (!shown.length) { items.innerHTML = '<p class="muted">No hay reportes en este estado.</p>'; return; }
  items.innerHTML = String(html`${shown.map((r) => html`<article class="card" data-id="${r.id}">
    ${r.has_photo ? html`<img alt="Foto del reporte" data-photo="${r.id}" />` : html`<div class="empty">Sin foto</div>`}
    <div class="card-title" style="margin-top:8px">${r.kind_label}</div>
    <div class="card-sub">${r.comuna || 'Sin comuna'} · ${fmtDateTime(r.created_at)} · ${ago(r.created_at)}</div>
    ${r.corroboraciones ? html`<div class="tiny" style="margin-top:4px"><b>${r.corroboraciones === 1 ? '1 vecino más lo corroboró' : `${r.corroboraciones} vecinos más lo corroboraron`}</b></div>` : ''}
    <p class="small" style="margin-top:6px">${r.description || 'Sin descripción.'}</p>
    <a class="tiny" href="https://www.openstreetmap.org/?mlat=${r.lat}&mlon=${r.lon}#map=14/${r.lat}/${r.lon}" target="_blank" rel="noopener">${r.lat.toFixed(4)}, ${r.lon.toFixed(4)} ↗</a>
    <input class="input" placeholder="Nota (cómo se verificó)" data-note style="margin-top:8px" value="${r.moderator_note || ''}" />
    <div class="card-actions"><button class="btn btn-sm btn-primary" data-set="verificado">Verificar</button>
      <button class="btn btn-sm btn-danger" data-set="descartado">Descartar</button>
      ${r.status !== 'no_verificado' ? html`<button class="btn btn-sm btn-ghost" data-set="no_verificado">Volver a pendiente</button>` : ''}</div>
  </article>`)}`);
  items.querySelectorAll('[data-photo]').forEach(async (img) => { const url = await photoUrl(img.dataset.photo); if (url) img.src = url; });
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

/* Pestaña Salud (OPS-01/OPS-14): qué fuente falló, si pasó el respaldo y cuántos puntos
 * quedaron fuera de Chile, sin abrir GitHub ni /api/status a mano. `saludResumen` es pura
 * (sin DOM ni fetch) para probarla con node --test; `renderSalud` solo la dibuja. */
export function saludResumen(status = {}, incidents = {}) {
  const ciclo = status?.last_cycle && typeof status.last_cycle === 'object' ? status.last_cycle : {};
  const frescura = status?.freshness || {};
  const backupError = typeof ciclo.backup_error === 'string' ? ciclo.backup_error.trim() : '';
  const porProducto = status?.failures_24h || status?.errors?.by_product || {};
  const fuentes = Object.entries(porProducto).map(([producto, p]) => ({
    producto,
    runs: p?.runs ?? 0,
    failed: p?.failed ?? 0,
    last_failed_at: p?.last_failed_at ?? null,
    last_error: p?.last_error ?? null,
  }));
  const lista = Array.isArray(incidents?.incidents) ? incidents.incidents : [];
  // «Fuera de Chile» = sin comuna y sin official_ref: /api/incidents ya publica solo
  // territorio chileno (comuna o CONAF), así que un caso así es una regresión del backend.
  const afuera = lista.filter((i) => i && i.comuna_code == null && i.official_ref == null);
  // Incendios oficiales de CONAF sin comuna emparejada: son chilenos, pero su riesgo y
  // sus avisos quedan sin calcular hasta asignarles una comuna por coordenadas.
  const sinComuna = lista.filter((i) => i && i.comuna_code == null && i.official_ref != null);
  // Los *_error del ciclo llegan como nombres de clave; los del respaldo ya cuentan en su tarjeta.
  const errores = [
    ...(ciclo.error ? [String(ciclo.error)] : []),
    ...(Array.isArray(status?.errors?.cycle_errors) ? status.errors.cycle_errors : []),
  ].filter((e) => e !== 'backup_error' && e !== 'restore_error');
  const respaldoMalo = ciclo.backup === false || Boolean(backupError) || Boolean(ciclo.restore_error);
  const metas = [];
  if (ciclo.backup === false) metas.push('db/brasa.db');
  // `work_backup: false` a secas no es falla: work.db se sube una vez por hora, no en cada
  // ciclo; solo cuenta cuando el error del respaldo lo menciona o coincide con su mensaje.
  if ((ciclo.work_backup === false && backupError) || /\bwork\b/i.test(backupError)) metas.push('db/work.db.gz');
  if (respaldoMalo && !metas.length) metas.push('db/brasa.db');
  const problemas = (respaldoMalo ? 1 : 0) + (frescura.stale === true ? 1 : 0)
    + fuentes.filter((f) => f.failed > 0).length + errores.length
    + (afuera.length ? 1 : 0) + (sinComuna.length ? 1 : 0);
  return {
    problemas,
    estado: problemas === 0 ? 'al día' : `${problemas} ${problemas === 1 ? 'problema' : 'problemas'}`,
    ciclo: {
      finished_at: ciclo.finished_at ?? null,
      last_ingest_at: status?.last_ingest_at ?? frescura.last_ingest_at ?? null,
      stale: frescura.stale === true,
      backup: ciclo.backup ?? null,
      work_backup: ciclo.work_backup ?? null,
      backup_error: backupError || null,
      errores,
      que_hacer: respaldoMalo
        ? `Revisar ${metas.map((m) => `/_internal/storage/${m}`).join(' y ')} en el Worker (error: ${backupError || ciclo.restore_error || 'sin mensaje'}).`
        : null,
    },
    fuentes,
    territorio: {
      fuera: afuera.length,
      sin_comuna: sinComuna.length,
      muestra: [...afuera, ...sinComuna].slice(0, 5).map((i) => ({ id: i.id, lat: i.lat, lon: i.lon, nombre: i.official_name ?? null })),
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

async function loadSalud() {
  const items = $('#salud-items');
  try {
    const [statusData, incidentsData] = await Promise.all([call('/api/status'), call('/api/incidents?limit=500')]);
    renderSalud(saludResumen(statusData, incidentsData));
  } catch (err) {
    toast(err.message, 'error');
    items.innerHTML = '<p class="muted">No se pudo leer el estado de la ingesta.</p>';
  }
}

function renderSalud(r) {
  const marca = (v) => (v === true ? 'sí' : v === false ? 'no' : 'sin dato');
  const malo = (bien) => (bien ? '' : ' style="color:var(--danger)"');
  $('#salud-estado').textContent = r.problemas ? `${r.estado} por mirar.` : 'Todo al día.';
  $('#salud-items').innerHTML = String(html`
    <article class="card">
      <div class="card-title">Ciclo y respaldo</div>
      <div class="card-sub"${malo(!r.ciclo.stale)}>Última ingesta ${fmtDateTime(r.ciclo.last_ingest_at)} · ${ago(r.ciclo.last_ingest_at)}${r.ciclo.stale ? ' · dato viejo' : ''}</div>
      <p class="small" style="margin-top:6px"${malo(!r.ciclo.backup_error && r.ciclo.backup !== false)}>Respaldo: ${marca(r.ciclo.backup)} · datos de trabajo: ${r.ciclo.work_backup === false && !r.ciclo.backup_error ? 'aún no (se sube cada hora)' : marca(r.ciclo.work_backup)}</p>
      ${r.ciclo.backup_error ? html`<p class="tiny" style="color:var(--danger)">${r.ciclo.backup_error}</p>` : ''}
      ${r.ciclo.errores.length ? html`<p class="tiny" style="color:var(--danger)">También falló: ${r.ciclo.errores.join(', ')}</p>` : ''}
      ${r.ciclo.que_hacer ? html`<p class="small"><b>Qué hacer:</b> ${r.ciclo.que_hacer}</p>` : ''}
    </article>
    <article class="card">
      <div class="card-title">Fuentes</div>
      ${r.fuentes.length ? r.fuentes.map((f) => html`<p class="small" style="margin-top:6px"${malo(!f.failed)}>${f.producto}: ${f.runs} corridas en 24 h, ${f.failed} ${f.failed === 1 ? 'fallida' : 'fallidas'}${f.last_failed_at ? html` · última ${ago(f.last_failed_at)}` : ''}${f.last_error ? html`<br><span class="tiny">${f.last_error}</span>` : ''}</p>`)
      : html`<p class="small muted">Sin corridas registradas en las últimas 24 h.</p>`}
      ${r.fuentes.some((f) => f.failed) ? html`<p class="small"><b>Qué hacer:</b> reintentar la fuente en el próximo ciclo y revisar el último issue que abrió el monitoreo; si es FIRMS, mirar el cupo en <code>/api/status</code>.</p>` : ''}
    </article>
    <article class="card">
      <div class="card-title">Territorio</div>
      <p class="small" style="margin-top:6px"${malo(!r.territorio.fuera && !r.territorio.sin_comuna)}>${territorioLinea(r.territorio)}</p>
      ${r.territorio.muestra.map((i) => html`<p class="tiny muted">${i.id}${i.nombre ? ` · ${i.nombre}` : ''} · ${i.lat}, ${i.lon}</p>`)}
      ${r.territorio.que_hacer ? html`<p class="small"><b>Qué hacer:</b> ${r.territorio.que_hacer}</p>` : ''}
    </article>`);
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
$('#comuna').addEventListener('change', () => { comunaFilter = $('#comuna').value; load(); });
document.querySelectorAll('[data-status]').forEach((b) => b.addEventListener('click', () => {
  status = b.dataset.status;
  document.querySelectorAll('[data-status]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  load();
}));
if (token) enter();
}
