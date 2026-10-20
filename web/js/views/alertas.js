/* Historial de alertas: todo lo que BRASA avisó a este dispositivo, con qué pasó y por dónde salió.
 * La identidad es el token del dispositivo; no hay cuentas ni correos. */
import { api } from '../api.js';
import { show } from '../map.js';
import { $, ago, dual, fmtDateTime, fmtNum, html, keepPlace, toast } from '../util.js';

let mounted = false;
let state = { alerts: [], total: 0, nextBefore: null, filter: 'todas', place: '', loading: false, error: '' };

const LEVELS = { urgente: { label: 'Urgente', cls: 'st-urgente' }, aviso: { label: 'Aviso', cls: 'st-aviso' } };
const FEEDBACK = { sirvio: 'Me sirvió', no_sirvio: 'No me sirvió', quema: 'Era una quema' };

function dayLabel(stamp) {
  return new Date(stamp).toLocaleDateString('es-CL', { timeZone: 'America/Santiago', weekday: 'long', day: 'numeric', month: 'long' });
}

/** De dónde salió el aviso, en palabras. Sin origen conocido no se muestra etiqueta: no se inventa un motivo. */
export function kindLabel(kind) {
  return { oficial: 'CONAF informa', reporte: 'Un vecino reportó', diario: 'Prevención del día', prueba: 'Prueba' }[kind] || '';
}

/** Canales por los que salió la alerta. Si no salió por ninguno, se dice: no se inventa un envío. */
function channels(list) {
  if (!list || !list.length) return 'No salió por ningún canal: la verás aquí cuando abras BRASA.';
  const names = { push: 'notificación del teléfono', telegram: 'Telegram' };
  return `Salió por ${list.map((c) => names[c] || c).join(' y ')}.`;
}

/** La fila de opinión: tres botones mientras el aviso no se evaluó; después, lo que quedó guardado. */
function feedback(a) {
  if (a.level === 'prueba') return '';
  if (a.feedback) return html`<div class="tiny muted" style="margin-top:4px">Tu opinión: «${FEEDBACK[a.feedback] || a.feedback}».</div>`;
  return html`<div class="btn-row" style="margin-top:6px;gap:6px" data-feedback="${a.id}">
    <span class="tiny muted">¿Te sirvió este aviso?</span>
    ${Object.entries(FEEDBACK).map(([value, label]) =>
      html`<button class="btn btn-sm btn-ghost" data-value="${value}">${label}</button>`)}
  </div>`;
}

function item(a) {
  const level = LEVELS[a.level] || { label: 'Aviso', cls: 'st-aviso' };
  const obs = a.observation || {};
  const kind = kindLabel(a.kind);
  const url = a.url || (a.kind === 'diario' ? '#/riesgo' : '');
  return html`<li>
    <span class="status-badge ${level.cls}">${level.label}</span>
    <div class="grow">
      <b class="small">${a.title}</b> ${kind ? html`<span class="tag">${kind}</span>` : ''}
      ${a.body ? html`<div class="tiny muted" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${a.body}</div>` : ''}
      <div class="tiny muted">${fmtDateTime(a.created_at)} · ${a.place?.name || 'tu lugar'}${a.distance_km != null ? ` · a ${fmtNum(a.distance_km)} km` : ''}</div>
      <div class="tiny muted">${channels(a.delivered)}</div>
      ${feedback(a)}
    </div>
    ${url ? html`<a class="btn btn-sm btn-ghost" href="${url}">Ver</a>` : ''}
  </li>`;
}

function groups(alerts) {
  const out = [];
  for (const a of alerts) {
    const day = dayLabel(a.created_at);
    const last = out[out.length - 1];
    if (last && last.day === day) last.items.push(a);
    else out.push({ day, items: [a] });
  }
  return out;
}

function body() {
  if (state.loading && !state.alerts.length) return html`<p class="small muted">Cargando tu historial…</p>`;
  if (state.error) return html`<div class="callout callout-warn"><b>No se pudo leer el historial.</b> ${state.error}</div>`;
  if (!state.alerts.length) {
    return html`<div class="empty" style="margin-top:16px"><div class="glyph">◌</div><b>Todavía no te hemos avisado de nada.</b>
      <p class="small">Cuando un satélite vea calor cerca de un lugar que guardaste, el aviso aparece aquí y te llega por los canales que activaste.</p></div>`;
  }
  const urgent = state.alerts.filter((a) => a.level === 'urgente').length;
  const places = [...new Set(state.alerts.map((a) => a.place?.name).filter(Boolean))];
  const place = places.includes(state.place) ? state.place : '';
  let visible = state.filter === 'urgentes' ? state.alerts.filter((a) => a.level === 'urgente') : state.alerts;
  if (place) visible = visible.filter((a) => (a.place?.name || '') === place);
  return html`
    <div class="kpis" style="margin-top:12px">
      <div class="kpi"><small>en total</small><strong>${fmtNum(state.total)}</strong><span>avisos</span></div>
      <div class="kpi"><small>en esta lista</small><strong>${fmtNum(state.alerts.length)}</strong><span>avisos</span></div>
      <div class="kpi"><small>urgentes</small><strong>${fmtNum(urgent)}</strong><span>en esta lista</span></div>
    </div>
    <div class="btn-row" style="margin-top:10px">
      <button class="btn btn-sm ${state.filter === 'todas' ? 'btn-primary' : 'btn-ghost'}" data-filter="todas">Todas</button>
      <button class="btn btn-sm ${state.filter === 'urgentes' ? 'btn-primary' : 'btn-ghost'}" data-filter="urgentes">Solo urgentes</button>
      ${places.length ? html`<select class="input" id="place-filter" aria-label="Filtrar por lugar" style="width:auto;max-width:100%">
        <option value="">Todos los lugares</option>
        ${places.map((p) => html`<option value="${p}"${p === place ? ' selected' : ''}>${p}</option>`)}
      </select>` : ''}
    </div>
    ${visible.length ? groups(visible).map((g) => html`
      <h2 class="section">${g.day}</h2>
      <ul class="list">${g.items.map(item)}</ul>`) : html`<p class="small muted" style="margin-top:12px">${place
        ? `Ningún aviso ${state.filter === 'urgentes' ? 'urgente ' : ''}de este lugar en la lista cargada.`
        : 'Ninguna alerta urgente en esta lista. Un aviso es «hay calor cerca»; urgente es «el viento va hacia ti o está muy cerca».'}</p>`}
    ${state.nextBefore ? html`<div class="btn-row" style="margin-top:14px"><button class="btn" id="more">Cargar avisos anteriores</button></div>` : ''}`;
}

function paint(container) {
  keepPlace(container, () => {
    container.querySelector('#inbox-body').innerHTML = String(body());
  });
  container.querySelectorAll('[data-filter]').forEach((b) => b.addEventListener('click', () => {
    state.filter = b.dataset.filter;
    paint(container);
  }));
  container.querySelector('#place-filter')?.addEventListener('change', (e) => {
    state.place = e.target.value;
    paint(container);
  });
  container.querySelectorAll('[data-feedback] button').forEach((b) => b.addEventListener('click', async () => {
    const id = Number(b.closest('[data-feedback]').dataset.feedback);
    try {
      const res = await api.feedbackAlert(id, b.dataset.value);
      const alert = state.alerts.find((x) => x.id === id);
      if (alert) alert.feedback = res.feedback;
      paint(container);
      toast('Gracias: nos ayuda a calibrar los avisos.');
    } catch (err) {
      toast(err.message, 'error');
    }
  }));
  container.querySelector('#more')?.addEventListener('click', () => load(container, true));
}

async function load(container, more = false) {
  if (state.loading) return;
  state.loading = true;
  state.error = '';
  if (!more) paint(container);
  try {
    const params = { limit: 50 };
    if (more && state.nextBefore) params.before = state.nextBefore;
    const data = await api.alerts(params);
    state.alerts = more ? [...state.alerts, ...(data.alerts || [])] : (data.alerts || []);
    state.total = data.total ?? state.alerts.length;
    state.nextBefore = data.next_before || null;
  } catch (err) {
    state.error = err.message;
  } finally {
    state.loading = false;
    if (mounted) {
      paint(container);
      // «Cargar avisos anteriores» desaparece al llegar al final: el foco va al último aviso.
      if (more && !container.querySelector('#more')) {
        const last = container.querySelector('#inbox-body ul.list:last-of-type li:last-child');
        if (last) { last.tabIndex = -1; last.focus({ preventScroll: true }); }
      }
    }
  }
}

export default {
  id: 'alertas',
  sheet: 'full',
  async mount(container) {
    mounted = true;
    show(['risk-fill', 'case-footprint-fill', 'case-footprint-line', 'case-points', 'case-goes', 'case-final',
      'case-event', 'explore', 'place-radius-fill', 'place-radius-line'], false);
    $('#map-legend').innerHTML = '';
    container.innerHTML = String(html`
      <h1 class="view-title">Lo que te hemos avisado</h1>
      <p class="lede">${dual('Cada aviso que recibiste, con la hora, el lugar y por dónde te llegó.',
        'Historial de alertas del dispositivo. La identidad es el token guardado en este navegador: no hay cuentas ni correos, y el historial no se comparte con otros dispositivos.')}</p>
      <div id="inbox-body"></div>
      <p class="tiny muted" style="margin-top:16px">Las alertas de BRASA no son alertas oficiales: si la autoridad ordena evacuar, hazlo. Emergencias: <a href="tel:130">130</a> CONAF · <a href="tel:132">132</a> Bomberos.</p>`);
    await load(container);
  },
  unmount() {
    mounted = false;
  },
};
