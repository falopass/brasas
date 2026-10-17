/* Componentes de interfaz compartidos: modal, emergencias, alta de lugares, reportes y canales de alerta. */
import { api } from './api.js';
import { getMap, setData } from './map.js';
import { enablePush, pushState } from './push.js';
import { store } from './store.js';
import { $, html, raw, toast } from './util.js';

export function openModal(fragment, onMount) {
  const dialog = $('#modal');
  $('#modal-body').innerHTML = String(fragment);
  if (!dialog.open) dialog.showModal();
  onMount?.($('#modal-body'), dialog);
  return dialog;
}
export const closeModal = () => $('#modal').open && $('#modal').close();

export const PHONES = [
  { n: '130', label: 'CONAF · incendios forestales', primary: true },
  { n: '132', label: 'Bomberos', primary: true },
  { n: '131', label: 'SAMU · ambulancia' },
  { n: '133', label: 'Carabineros' },
  { n: '134', label: 'PDI' },
  { n: '*4242', label: 'Denuncia Seguro (anónimo)', tel: '*4242' },
];
export const phonesHtml = () => html`<div class="phones">${PHONES.map((p) => html`
  <a class="phone ${p.primary ? 'primary' : ''}" href="tel:${p.tel || p.n}"><strong>${p.n}</strong><span>${p.label}</span></a>`)}</div>`;

export function openEmergency() {
  openModal(html`
    <h2 id="modal-title">Emergencias</h2>
    <p class="muted small">Si ves fuego o humo cerca, llama de inmediato. No esperes a que aparezca en un satélite.</p>
    ${phonesHtml()}
    <div class="callout callout-warn" style="margin-top:14px">
      <b>Si la autoridad ordena evacuar, hazlo de inmediato.</b> Sigue las instrucciones de SENAPRED y los mensajes del
      Sistema de Alerta de Emergencia (SAE) en tu celular. BRASA no emite alertas oficiales.
    </div>
    <div class="btn-row" style="margin-top:12px">
      <a class="btn btn-sm" href="https://senapred.cl/" target="_blank" rel="noopener">SENAPRED ↗</a>
      <a class="btn btn-sm" href="https://www.conaf.cl/" target="_blank" rel="noopener">CONAF ↗</a>
      <a class="btn btn-sm" href="#/preparate" data-close>Qué hacer ↗</a>
    </div>`, (body) => body.querySelectorAll('[data-close]').forEach((a) => a.addEventListener('click', closeModal)));
}

// ------------------------------------------------------------------ elegir un punto en el mapa
let pickResolver = null;
export function pickOnMap(prompt = 'Toca el mapa para elegir la ubicación') {
  closeModal();
  const map = getMap();
  const hint = $('#pick-hint');
  hint.querySelector('span').textContent = prompt;
  hint.hidden = false;
  document.body.classList.add('picking');
  collapseSheet();
  return new Promise((resolve) => {
    pickResolver = resolve;
    const done = (value) => {
      hint.hidden = true;
      document.body.classList.remove('picking');
      map.off('click', onClick);
      pickResolver = null;
      resolve(value);
    };
    const onClick = (e) => done({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    map.once('click', onClick);
    $('#pick-cancel').onclick = () => { map.off('click', onClick); done(null); };
  });
}
export const isPicking = () => pickResolver !== null;

export function collapseSheet() { document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'peek' })); }
export function expandSheet() { document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'half' })); }

// ------------------------------------------------------------------ alta y edición de lugares
const KIND_LABELS = { casa: 'Mi casa', parcela: 'Parcela / campo', familia: 'Familia', trabajo: 'Trabajo', colegio: 'Colegio', otro: 'Otro' };

export function placeForm(existing = null, preset = null) {
  const comunas = store.get('comunasIndex') || [];
  const draft = {
    name: existing?.name || '', kind: existing?.kind || 'casa', radius_km: existing?.radius_km || 10,
    point: existing ? { lat: existing.lat, lon: existing.lon } : preset,
  };
  const readInputs = (body) => {
    draft.name = body.querySelector('#pf-name').value;
    draft.radius_km = Number(body.querySelector('#pf-radius').value);
  };
  const clearPick = () => setData('pick', { type: 'FeatureCollection', features: [] });
  const render = () => openModal(html`
    <h2 id="modal-title">${existing ? 'Editar lugar' : 'Agregar un lugar'}</h2>
    <p class="muted small">Te avisaremos cuando aparezca un foco de calor satelital dentro del radio. Puedes guardar hasta 10 lugares.</p>
    <form id="place-form">
      <div class="field"><label for="pf-name">Nombre</label>
        <input class="input" id="pf-name" required maxlength="60" placeholder="Ej.: Casa de mis papás" value="${draft.name}" /></div>
      <div class="field"><span class="label">Tipo</span>
        <div class="chips" id="pf-kind">${Object.entries(KIND_LABELS).map(([k, label]) => html`
          <button type="button" class="chip" data-kind="${k}" aria-pressed="${draft.kind === k}">${label}</button>`)}</div></div>
      <div class="field"><span class="label">Ubicación</span>
        <div class="callout small" id="pf-point">${draft.point ? `Punto ${draft.point.lat.toFixed(4)}, ${draft.point.lon.toFixed(4)}` : 'Aún no eliges la ubicación.'}</div>
        <div class="btn-row" style="margin-top:8px">
          <button type="button" class="btn btn-sm" id="pf-gps">◎ Usar mi ubicación</button>
          <button type="button" class="btn btn-sm" id="pf-map">⌖ Elegir en el mapa</button>
        </div>
        <input class="input" id="pf-comuna" list="pf-comunas" placeholder="…o escribe una comuna" style="margin-top:8px" autocomplete="off" />
        <datalist id="pf-comunas">${comunas.map((c) => html`<option value="${c.name}">${c.region}</option>`)}</datalist>
      </div>
      <div class="field"><label for="pf-radius">Radio de alerta</label>
        <select class="input" id="pf-radius">${[5, 10, 15, 20, 30].map((r) => html`<option value="${r}" ${draft.radius_km === r ? raw('selected') : ''}>${r} km</option>`)}</select>
        <span class="tiny muted">Sugerencia: 10 km en zonas urbanas; 15–20 km en sectores rurales o con viento fuerte.</span></div>
      <div class="btn-row"><button class="btn btn-primary" type="submit">${existing ? 'Guardar cambios' : 'Guardar lugar'}</button>
        <button class="btn btn-ghost" type="button" data-cancel>Cancelar</button></div>
    </form>`, (body) => {
    body.querySelectorAll('#pf-kind .chip').forEach((chip) => chip.addEventListener('click', () => {
      draft.kind = chip.dataset.kind;
      body.querySelectorAll('#pf-kind .chip').forEach((c) => c.setAttribute('aria-pressed', String(c === chip)));
      const name = body.querySelector('#pf-name');
      if (!name.value || Object.values(KIND_LABELS).includes(name.value)) name.value = KIND_LABELS[draft.kind];
    }));
    const setPoint = (p) => { draft.point = p; body.querySelector('#pf-point').textContent = `Punto ${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}`; };
    body.querySelector('#pf-gps').addEventListener('click', () => {
      if (!navigator.geolocation) return toast('Tu navegador no permite geolocalización.', 'error');
      navigator.geolocation.getCurrentPosition((pos) => setPoint({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
        () => toast('No fue posible obtener tu ubicación. Revisa los permisos.', 'error'), { enableHighAccuracy: true, timeout: 12000 });
    });
    body.querySelector('#pf-map').addEventListener('click', async () => {
      readInputs(body);
      const picked = await pickOnMap('Toca el lugar que quieres vigilar');
      if (picked) {
        draft.point = picked;
        setData('pick', { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [picked.lon, picked.lat] }, properties: {} }] });
      }
      render();
    });
    body.querySelector('#pf-comuna').addEventListener('change', (e) => {
      const c = comunas.find((x) => x.name.toLowerCase() === e.target.value.trim().toLowerCase());
      if (c) setPoint({ lat: c.center[1], lon: c.center[0] });
    });
    body.querySelector('[data-cancel]').addEventListener('click', () => { clearPick(); closeModal(); });
    body.querySelector('#place-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      readInputs(body);
      if (!draft.point) return toast('Elige la ubicación del lugar.', 'error');
      const payload = { name: draft.name.trim(), kind: draft.kind, lat: draft.point.lat, lon: draft.point.lon, radius_km: draft.radius_km };
      try {
        if (existing?.id) await api.updatePlace(existing.id, payload); else await api.addPlace(payload);
        clearPick();
        closeModal();
        toast(existing?.id ? 'Lugar actualizado.' : 'Lugar guardado. Activa las alertas para recibir avisos.');
        document.dispatchEvent(new CustomEvent('brasa:places-changed'));
      } catch (err) { toast(err.message, 'error'); }
    });
  });
  render();
}


// ------------------------------------------------------------------ canales de alerta
export async function alertChannels() {
  const config = store.get('config');
  let me = { push: false, telegram: false };
  try { me = await api.me(); } catch { /* sin token aún */ }
  const push = await pushState();
  openModal(html`
    <h2 id="modal-title">Recibir alertas</h2>
    <p class="muted small">Elige uno o más canales. Las alertas llegan cuando hay un foco de calor confiable dentro del radio de tus lugares, y se marcan como <b>URGENTE</b> si el viento sopla desde el foco hacia ti.</p>
    <div class="card">
      <div class="card-head"><div><div class="card-title">Notificaciones en este dispositivo</div>
        <div class="card-sub">${push.supported ? (me.push ? 'Activadas.' : 'Funciona mejor con BRASA instalada en la pantalla de inicio.') : 'Este navegador no admite notificaciones web.'}</div></div>
        <span class="tag ${me.push ? 'tag-live' : ''}">${me.push ? 'Activo' : 'Inactivo'}</span></div>
      <div class="card-actions">${push.supported ? html`<button class="btn btn-sm btn-primary" id="ch-push">${me.push ? 'Reactivar' : 'Activar notificaciones'}</button>` : ''}</div>
    </div>
    <div class="card">
      <div class="card-head"><div><div class="card-title">Telegram</div>
        <div class="card-sub">${config?.telegram?.enabled ? 'Recibe las alertas en Telegram, aunque no tengas BRASA abierta.' : 'Este servidor aún no tiene un bot de Telegram configurado.'}</div></div>
        <span class="tag ${me.telegram ? 'tag-live' : ''}">${me.telegram ? 'Vinculado' : 'No vinculado'}</span></div>
      <div class="card-actions">${config?.telegram?.enabled ? html`<button class="btn btn-sm" id="ch-telegram">${me.telegram ? 'Volver a vincular' : 'Vincular Telegram'}</button>` : ''}</div>
    </div>
    <div class="btn-row" style="margin-top:14px">
      <button class="btn btn-sm btn-ghost" id="ch-test" ${me.push || me.telegram ? '' : raw('disabled')}>Enviar alerta de prueba</button>
    </div>
    <p class="tiny muted" style="margin-top:12px">BRASA no reemplaza el Sistema de Alerta de Emergencia (SAE) de SENAPRED en tu celular: mantenlo activo.</p>`, (body) => {
    body.querySelector('#ch-push')?.addEventListener('click', async () => {
      try { await enablePush(config.push.public_key); toast('Notificaciones activadas.'); alertChannels(); } catch (err) { toast(err.message, 'error'); }
    });
    body.querySelector('#ch-telegram')?.addEventListener('click', async () => {
      try { const { url } = await api.telegramLink(); window.open(url, '_blank', 'noopener'); toast('Abre el bot y pulsa «Iniciar» para terminar.'); } catch (err) { toast(err.message, 'error'); }
    });
    body.querySelector('#ch-test')?.addEventListener('click', async () => {
      try { const { channels } = await api.testAlert(); toast(channels.length ? `Prueba enviada por: ${channels.join(', ')}.` : 'No se pudo entregar la prueba. Revisa los canales.', channels.length ? 'info' : 'error'); } catch (err) { toast(err.message, 'error'); }
    });
  });
}

// ------------------------------------------------------------------ reportes ciudadanos
export function reportForm(preset = null) {
  let point = preset;
  openModal(html`
    <h2 id="modal-title">Reportar humo o fuego</h2>
    <div class="callout callout-urgent small"><b>¿Ves llamas o humo cerca?</b> Llama primero al <a href="tel:130"><b>130</b></a> (CONAF) o al <a href="tel:132"><b>132</b></a> (Bomberos). Este reporte no reemplaza esa llamada.</div>
    <form id="report-form" style="margin-top:14px">
      <div class="field"><span class="label">¿Qué ves?</span>
        <div class="segmented" id="rf-kind">${[['humo', 'Humo'], ['llamas', 'Llamas'], ['quema', 'Quema / fogata'], ['otro', 'Otro']].map(([k, l], i) => html`
          <button type="button" data-kind="${k}" aria-pressed="${i === 0}">${l}</button>`)}</div></div>
      <div class="field"><span class="label">Ubicación aproximada</span>
        <div class="callout small" id="rf-point">${point ? `Punto ${point.lat.toFixed(4)}, ${point.lon.toFixed(4)}` : 'Usa tu ubicación o el centro del mapa.'}</div>
        <div class="btn-row" style="margin-top:8px"><button type="button" class="btn btn-sm" id="rf-gps">◎ Mi ubicación</button>
          <button type="button" class="btn btn-sm" id="rf-center">⌖ Centro del mapa</button></div></div>
      <div class="field"><label for="rf-desc">Descripción (opcional)</label>
        <textarea class="input" id="rf-desc" maxlength="600" placeholder="Ej.: columna de humo blanco hacia el cerro, viento hacia el oriente"></textarea></div>
      <div class="field"><label for="rf-photo">Foto (opcional)</label>
        <input class="input" type="file" id="rf-photo" accept="image/*" capture="environment" />
        <span class="tiny muted">Eliminamos los metadatos de la foto (incluida la ubicación GPS del archivo).</span></div>
      <p class="tiny muted">Tu reporte lo revisa un voluntario antes de mostrarse. No pedimos tu nombre ni teléfono.</p>
      <button class="btn btn-primary btn-block" type="submit">Enviar reporte</button>
    </form>`, (body) => {
    let kind = 'humo';
    body.querySelectorAll('#rf-kind button').forEach((b) => b.addEventListener('click', () => {
      kind = b.dataset.kind; body.querySelectorAll('#rf-kind button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    }));
    const setPoint = (p) => { point = p; body.querySelector('#rf-point').textContent = `Punto ${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}`; };
    body.querySelector('#rf-gps').addEventListener('click', () => navigator.geolocation?.getCurrentPosition(
      (pos) => setPoint({ lat: pos.coords.latitude, lon: pos.coords.longitude }), () => toast('No fue posible obtener tu ubicación.', 'error'), { enableHighAccuracy: true, timeout: 12000 }));
    body.querySelector('#rf-center').addEventListener('click', () => { const c = getMap().getCenter(); setPoint({ lat: c.lat, lon: c.lng }); });
    body.querySelector('#report-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!point) return toast('Indica la ubicación del reporte.', 'error');
      const form = new FormData();
      form.set('lat', String(point.lat)); form.set('lon', String(point.lon)); form.set('kind', kind);
      form.set('description', body.querySelector('#rf-desc').value);
      const file = body.querySelector('#rf-photo').files[0];
      if (file) form.set('photo', file);
      try {
        const res = await api.createReport(form);
        openModal(html`<h2 id="modal-title">Reporte recibido</h2><p>${res.message}</p>${phonesHtml()}`);
      } catch (err) { toast(err.message, 'error'); }
    });
  });
}
