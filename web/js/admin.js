/* Moderación de reportes ciudadanos. El token vive solo en la sesión del navegador. */
import { $, fmtDateTime, html, toast } from './util.js';

let token = sessionStorage.getItem('brasa:admin') || '';
let status = 'no_verificado';

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

async function load() {
  let data;
  try { data = await call(`/api/admin/reports?status=${status}`); } catch (err) {
    toast(err.message, 'error'); $('#queue').hidden = true; $('#login').hidden = false; return;
  }
  $('#login').hidden = true; $('#queue').hidden = false;
  releasePhotos();
  const items = $('#items');
  if (!data.reports.length) { items.innerHTML = '<p class="muted">No hay reportes en este estado.</p>'; return; }
  items.innerHTML = String(html`${data.reports.map((r) => html`<article class="card" data-id="${r.id}">
    ${r.has_photo ? html`<img alt="Foto del reporte" data-photo="${r.id}" />` : html`<div class="empty">Sin foto</div>`}
    <div class="card-title" style="margin-top:8px">${r.kind_label}</div>
    <div class="card-sub">${r.comuna || 'Sin comuna'} · ${fmtDateTime(r.created_at)}</div>
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

$('#login').addEventListener('submit', (e) => {
  e.preventDefault();
  token = $('#token').value.trim();
  sessionStorage.setItem('brasa:admin', token);
  load();
});
document.querySelectorAll('[data-status]').forEach((b) => b.addEventListener('click', () => {
  status = b.dataset.status;
  document.querySelectorAll('[data-status]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  load();
}));
if (token) load();
