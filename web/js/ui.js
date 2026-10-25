/* Componentes de interfaz compartidos: modal, emergencias, alta de lugares, reportes y canales de alerta. */
import { api, request } from './api.js';
import { fitDimensions, shouldShrink } from './foto.js';
import { getMap, setData } from './map.js';
import { disablePush, enablePush, pushState } from './push.js';
import { caducado, cercanos, descartar, distancia, FOCOS_HORAS, FOCOS_KM, guardar, latest, line, marcarEnviado, pendientes, resumenCercanos, resumenFocos, testigos } from './reportes.js';
import { store } from './store.js';
import { $, dual, html, raw, storage, toast } from './util.js';

export function openModal(fragment, onMount) {
  const dialog = $('#modal');
  const body = $('#modal-body');
  const wasOpen = dialog.open;
  // Al repintar un modal abierto, el control enfocado desaparece del DOM y el foco cae al <body>:
  // se guarda un identificador estable (id o el primer atributo data-*), como hace keepPlace().
  const active = wasOpen && body.contains(document.activeElement) ? document.activeElement : null;
  const data = active && !active.id ? [...active.attributes].find((a) => a.name.startsWith('data-')) : null;
  const key = active && (active.id ? `#${CSS.escape(active.id)}` : data && `[${data.name}="${CSS.escape(data.value)}"]`);
  body.innerHTML = String(fragment);
  if (!wasOpen) dialog.showModal();
  onMount?.(body, dialog);
  if (wasOpen) {
    const target = (key && body.querySelector(key))
      || [...body.querySelectorAll('a[href], button, input, select, textarea, [tabindex]')].find((el) => !el.disabled && el.tabIndex >= 0);
    target?.focus({ preventScroll: true });
  }
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
    <p class="muted small">Si ves fuego o humo cerca, llama de inmediato. No esperes a que lo vea un satélite.</p>
    ${phonesHtml()}
    <div class="callout callout-warn" style="margin-top:14px">
      <b>Si la autoridad ordena evacuar, hazlo de inmediato.</b> Sigue las instrucciones de SENAPRED y los mensajes de
      emergencia que llegan a tu celular. BRASA es una ayuda ciudadana, no una alerta oficial.
    </div>
    <div class="btn-row" style="margin-top:12px">
      <a class="btn btn-sm btn-primary" href="#/quehago" data-close>¿Qué hago si…?</a>
      <a class="btn btn-sm" href="https://senapred.cl/" target="_blank" rel="noopener">SENAPRED ↗</a>
      <a class="btn btn-sm" href="https://www.conaf.cl/" target="_blank" rel="noopener">CONAF ↗</a>
      <a class="btn btn-sm" href="#/preparate" data-close>Prepárate ↗</a>
    </div>`, (body) => body.querySelectorAll('[data-close]').forEach((a) => a.addEventListener('click', closeModal)));
}

// ------------------------------------------------------------------ elegir un punto en el mapa
let pickResolver = null;
let cancelPick = null;
export function pickOnMap(prompt = 'Toca el mapa para elegir la ubicación') {
  // Si ya había una elección en curso, se cancela antes de empezar otra (no quedan dos esperas abiertas).
  cancelPick?.();
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
      cancelPick = null;
      resolve(value);
    };
    const onClick = (e) => done({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    map.once('click', onClick);
    cancelPick = () => done(null);
    $('#pick-cancel').onclick = () => done(null);
  });
}

export function collapseSheet() { document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'peek' })); }
// ------------------------------------------------------------------ alta y edición de lugares
const KIND_LABELS = { casa: 'Mi casa', parcela: 'Parcela / campo', familia: 'Familia', trabajo: 'Trabajo', colegio: 'Colegio', otro: 'Otro' };

export function placeForm(existing = null, preset = null) {
  const comunas = store.get('comunasIndex') || [];
  const draft = {
    name: existing?.name || preset?.name || KIND_LABELS.casa, kind: existing?.kind || preset?.kind || 'casa',
    radius_km: existing?.radius_km || preset?.radius_km || 10, older_adult: existing?.older_adult ?? preset?.older_adult ?? false,
    daily_brief: existing?.daily_brief ?? preset?.daily_brief ?? false,
    point: existing ? { lat: existing.lat, lon: existing.lon } : (preset?.lat != null ? { lat: preset.lat, lon: preset.lon } : null), where: null,
  };
  const readInputs = (body) => {
    draft.name = body.querySelector('#pf-name').value;
    draft.radius_km = Number(body.querySelector('#pf-radius').value);
    draft.older_adult = body.querySelector('#pf-older').checked;
    draft.daily_brief = body.querySelector('#pf-daily').checked;
  };
  const clearPick = () => setData('pick', { type: 'FeatureCollection', features: [] });
  const pointText = () => (draft.point
    ? html`<b>Ubicación lista.</b> ${draft.where ? `En ${draft.where}.` : ''} ${dual('', `${draft.point.lat.toFixed(4)}, ${draft.point.lon.toFixed(4)}`)}`
    : 'Aún no eliges dónde está.');
  const render = () => openModal(html`
    <h2 id="modal-title">${existing ? 'Editar lugar' : 'Agregar un lugar'}</h2>
    <p class="muted small">Te avisamos si un satélite ve calor cerca de este lugar. Puedes guardar hasta 10.</p>
    <form id="place-form" class="q-form">
      <div class="field"><span class="label"><span class="q-n">1</span>¿Dónde está?</span>
        <div class="btn-row">
          <button type="button" class="btn" id="pf-gps">Estoy aquí ahora</button>
          <button type="button" class="btn" id="pf-map">Marcarlo en el mapa</button>
        </div>
        <input class="input" id="pf-comuna" list="pf-comunas" placeholder="…o escribe tu comuna" style="margin-top:8px" autocomplete="off" />
        <datalist id="pf-comunas">${comunas.map((c) => html`<option value="${c.name}">${c.region}</option>`)}</datalist>
        <div class="callout small ${draft.point ? 'callout-ok' : ''}" id="pf-point" style="margin-top:8px">${pointText()}</div>
      </div>
      <div class="field"><span class="label"><span class="q-n">2</span>¿Qué es?</span>
        <div class="chips" id="pf-kind">${Object.entries(KIND_LABELS).map(([k, label]) => html`
          <button type="button" class="chip" data-kind="${k}" aria-pressed="${draft.kind === k}">${label}</button>`)}</div></div>
      <div class="field"><label for="pf-name"><span class="q-n">3</span>¿Cómo lo llamamos?</label>
        <input class="input" id="pf-name" required maxlength="60" placeholder="Ej.: Casa de mis papás" value="${draft.name}" /></div>
      <div class="field"><label for="pf-radius"><span class="q-n">4</span>Avísame si hay calor a menos de…</label>
        <select class="input" id="pf-radius">${[5, 10, 15, 20, 30].map((r) => html`<option value="${r}" ${draft.radius_km === r ? raw('selected') : ''}>${r} km</option>`)}</select>
        <span class="tiny muted">En la ciudad bastan 10 km. En el campo o con mucho viento, mejor 15 a 20 km.</span></div>
      <div class="field"><span class="label"><span class="q-n">5</span>¿Vive aquí alguien que necesite ayuda para salir?</span>
        <label class="older-check"><input type="checkbox" id="pf-older" ${draft.older_adult ? raw('checked') : ''} />
          <span><b>Sí, una persona mayor</b> o alguien con movilidad reducida, enfermedad o sin auto.
          <span class="tiny muted" style="display:block">Es opcional y solo cambia una cosa: cualquier calor dentro del radio se avisa como «urgente» (más tiempo para ayudarla a salir). La marca queda guardada junto al lugar y, si compartes el enlace familiar, quien lo abra también la verá: te avisamos antes de compartir. No la usamos para nada más.</span></span></label></div>
      <div class="field"><span class="label"><span class="q-n">6</span>¿Un aviso en la mañana cuando haya riesgo?</span>
        <label class="older-check"><input type="checkbox" id="pf-daily" ${draft.daily_brief ? raw('checked') : ''} />
          <span><b>Recibir un aviso al día cuando haya riesgo alto (a las 8:00).</b>
          <span class="tiny muted" style="display:block">Un solo mensaje en la mañana y solo los días con Botón Rojo o riesgo alto en tu comuna; si el día es normal, no llega nada. Es opcional y los avisos de calor cercano llegan igual, esté marcada o no.</span></span></label></div>
      <div class="btn-row"><button class="btn btn-primary" type="submit">${existing ? 'Guardar cambios' : 'Guardar lugar'}</button>
        <button class="btn btn-ghost" type="button" data-cancel>Cancelar</button></div>
      <p class="tiny muted">Al guardar, aceptas la <a href="#/privacidad" data-close>política de privacidad</a>.</p>
    </form>`, (body) => {
    body.querySelectorAll('#pf-kind .chip').forEach((chip) => chip.addEventListener('click', () => {
      draft.kind = chip.dataset.kind;
      body.querySelectorAll('#pf-kind .chip').forEach((c) => c.setAttribute('aria-pressed', String(c === chip)));
      const name = body.querySelector('#pf-name');
      if (!name.value || Object.values(KIND_LABELS).includes(name.value)) name.value = KIND_LABELS[draft.kind];
    }));
    const showPoint = () => {
      const el = body.querySelector('#pf-point');
      el.innerHTML = String(pointText());
      el.classList.toggle('callout-ok', Boolean(draft.point));
    };
    const setPoint = async (p, where = null) => {
      draft.point = p; draft.where = where; showPoint();
      if (!where) {
        try { const { comuna } = await api.locate(p.lat, p.lon); draft.where = comuna ? `${comuna.name}, ${comuna.region}` : 'un lugar fuera de las comunas de Chile'; } catch { /* sin conexión: basta la ubicación */ }
        showPoint();
      }
    };
    if (draft.point && !draft.where) setPoint(draft.point);
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
      if (c) setPoint({ lat: c.center[1], lon: c.center[0] }, `el centro de ${c.name}, ${c.region}`);
    });
    body.querySelectorAll('[data-close]').forEach((a) => a.addEventListener('click', () => { clearPick(); closeModal(); }));
    body.querySelector('[data-cancel]').addEventListener('click', () => { clearPick(); closeModal(); });
    body.querySelector('#place-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      readInputs(body);
      if (!draft.point) return toast('Primero dinos dónde está: usa «Estoy aquí ahora», el mapa o tu comuna.', 'error');
      const payload = { name: draft.name.trim(), kind: draft.kind, lat: draft.point.lat, lon: draft.point.lon, radius_km: draft.radius_km, older_adult: draft.older_adult, daily_brief: draft.daily_brief };
      try {
        const firstPlace = !existing?.id && !(store.get('places') || []).length && installStepsHtml() !== '';
        if (existing?.id) await api.updatePlace(existing.id, payload); else await api.addPlace(payload);
        clearPick();
        document.dispatchEvent(new CustomEvent('brasa:places-changed'));
        if (!existing?.id && await offerAlertTest()) { openAlertTest(); return; }
        closeModal();
        if (firstPlace) {
          toast('Lugar guardado. Para recibir avisos en este teléfono, agrega BRASA a tu pantalla de inicio.', 'info', 9000,
            { label: 'Ver cómo', onClick: openInstallGuide });
        } else {
          toast(existing?.id ? 'Lugar actualizado.' : 'Lugar guardado. Activa los avisos para enterarte aunque no tengas BRASA abierta.');
        }
      } catch (err) { toast(err.message, 'error'); }
    });
  });
  render();
}


// ------------------------------------------------------------------ instalar en la pantalla de inicio (UX-09)
// En iPhone los avisos web solo llegan si BRASA está agregada a la pantalla de inicio.
const isInstalled = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
/** iPhone/iPad (iPadOS se declara como Mac con pantalla táctil). */
const isIos = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

/** El control que hay que encontrar en cada sistema: Compartir (iOS), menú ⋮ (Android) e Instalar (escritorio). */
const INSTALL_SVG = {
  share: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 10H6.5a2 2 0 0 0-2 2v6.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V12a2 2 0 0 0-2-2h-2"/><path d="M12 14.5V3.5"/><path d="m8.5 7 3.5-3.5L15.5 7"/></svg>',
  menu: '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5.5" r="1.9"/><circle cx="12" cy="12" r="1.9"/><circle cx="12" cy="18.5" r="1.9"/></svg>',
  install: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4" width="17" height="12.5" rx="2"/><path d="M12 7.5v5.5"/><path d="m9.5 11 2.5 2.5L14.5 11"/><path d="M9 20h6"/></svg>',
};

/** Pasos para agregar BRASA a la pantalla de inicio, según el sistema. '' si ya está instalada. */
function installStepsHtml() {
  if (isInstalled()) return '';
  const ua = navigator.userAgent;
  const ios = isIos();
  const visual = ios ? INSTALL_SVG.share : /android/i.test(ua) ? INSTALL_SVG.menu : INSTALL_SVG.install;
  const steps = ios
    ? ['Abre BRASA en Safari.', 'Toca «Compartir» (el cuadrado con la flecha hacia arriba).', 'Elige «Añadir a pantalla de inicio» y luego «Agregar».']
    : /android/i.test(ua)
      ? ['Abre BRASA en Chrome.', 'Toca el menú ⋮ y elige «Instalar aplicación» o «Añadir a pantalla de inicio».']
      : ['En el menú del navegador, elige «Instalar BRASA» o «Guardar en pantalla de inicio».'];
  return html`<div class="install-visual">${raw(visual)}</div>
    <ol class="install-steps">${steps.map((s) => html`<li>${s}</li>`)}</ol>
    <p class="tiny muted">${ios ? 'En iPhone los avisos solo llegan si BRASA está en la pantalla de inicio.' : 'Instalada se abre de un toque, como una aplicación.'}
    Después ábrela desde el ícono nuevo y activa los avisos en «Recibir alertas».</p>`;
}

/** La guía plegable para los modales. */
function installGuideFold(summary, style) {
  const steps = installStepsHtml();
  return steps === '' ? '' : html`<details class="fold" style="${style}"><summary>${summary}</summary><div>${steps}</div></details>`;
}

function openInstallGuide() {
  openModal(html`<h2 id="modal-title">Agregar BRASA a tu pantalla de inicio</h2>${installStepsHtml()}`);
}

// ------------------------------------------------------------------ probar los avisos tras guardar un lugar (ALR-13)
// Se ofrece solo al crear un lugar (no al editar), mientras no se haya probado con éxito: si el
// navegador no admite avisos web, pedirla no tiene sentido.
async function offerAlertTest() {
  if (storage.get('avisoProbado')) return false;
  const { supported } = await pushState();
  return supported;
}

/** La instrucción para que los avisos lleguen, según el sistema. */
function alertGuideHtml() {
  const ua = navigator.userAgent;
  const ios = isIos();
  const visual = ios ? INSTALL_SVG.share : /android/i.test(ua) ? INSTALL_SVG.menu : '';
  const steps = ios
    ? ['En Safari, toca «Compartir» (el cuadrado con la flecha hacia arriba).',
       'Elige «Añadir a pantalla de inicio» y luego «Agregar».',
       'Abre BRASA desde el ícono nuevo y permite las notificaciones.']
    : /android/i.test(ua)
      ? ['Permite las notificaciones de este sitio cuando el navegador lo pida.',
         'Si las bloqueaste, actívalas en el menú ⋮ → «Configuración» → «Notificaciones».']
      : ['Permite las notificaciones del navegador cuando lo pida.',
         'Si las bloqueaste, actívalas en el candado junto a la dirección.'];
  return html`${visual ? html`<div class="install-visual">${raw(visual)}</div>` : ''}
    <ol class="steps">${steps.map((s) => html`<li>${s}</li>`)}</ol>
    ${ios ? html`<p class="tiny muted">En iPhone los avisos solo llegan si BRASA está en la pantalla de inicio.</p>` : ''}`;
}

/** El paso guiado: la instrucción por sistema y el botón de prueba (el endpoint ya existe).
 *  El resultado va dentro del modal: un <dialog> abierto tapa los avisos flotantes (toast). */
function openAlertTest() {
  openModal(html`
    <h2 id="modal-title">¿Te llegan los avisos?</h2>
    <p class="muted small">Guarda este paso: así sabrás que los avisos te llegan.</p>
    ${alertGuideHtml()}
    <div class="callout callout-warn small" id="at-result" style="margin-top:10px" hidden></div>
    <div class="btn-row" style="margin-top:12px">
      <button class="btn btn-primary" id="at-test" type="button">Probar aviso</button>
      <button class="btn btn-ghost" id="at-later" type="button">Ahora no</button>
    </div>`, (body) => {
    const result = body.querySelector('#at-result');
    const test = body.querySelector('#at-test');
    test.addEventListener('click', async () => {
      test.disabled = true;
      try {
        const { channels } = await api.testAlert();
        if (channels.length) {
          storage.set('avisoProbado', true);
          closeModal();
          toast(`Prueba enviada por: ${channels.join(', ')}.`);
        } else {
          result.hidden = false;
          result.innerHTML = String(html`No se pudo entregar la prueba. Activa los avisos y vuelve a probar.
            <div class="btn-row" style="margin-top:8px"><button class="btn btn-sm" id="at-channels" type="button">Activar avisos</button></div>`);
          result.querySelector('#at-channels').addEventListener('click', alertChannels);
        }
      } catch (err) {
        result.hidden = false;
        result.textContent = err.message;
      } finally {
        test.disabled = false;
      }
    });
    body.querySelector('#at-later').addEventListener('click', closeModal);
  });
}

// ------------------------------------------------------------------ canales de alerta
export async function alertChannels() {
  const config = store.get('config');
  let me = { push: false, telegram: false };
  try { me = await api.me(); } catch { /* sin token aún */ }
  const push = await pushState();
  openModal(html`
    <h2 id="modal-title">Recibir alertas</h2>
    <p class="muted small">Te avisamos aunque no tengas BRASA abierta, cuando un satélite vea calor cerca de tus lugares. Si además el viento va desde ese punto hacia ti, el aviso dice <b>URGENTE</b>.</p>
    <div class="card">
      <div class="card-head"><div><div class="card-title">Avisos en este teléfono</div>
        <div class="card-sub">${push.supported ? (me.push ? 'Activadas.' : 'Funciona mejor si agregas BRASA a la pantalla de inicio del teléfono.') : 'Este navegador no admite notificaciones web.'}</div></div>
        <span class="tag ${me.push ? 'tag-live' : ''}">${me.push ? 'Activo' : 'Inactivo'}</span></div>
      <div class="card-actions">${push.supported ? html`<button class="btn btn-sm btn-primary" id="ch-push">${me.push ? 'Reactivar' : 'Activar avisos'}</button>${me.push ? html`<button class="btn btn-sm btn-ghost" id="ch-push-off">Desactivar avisos</button>` : ''}` : ''}</div>
    </div>
    ${installGuideFold('Cómo activar los avisos en tu teléfono', 'margin:8px 0')}
    <div class="card">
      <div class="card-head"><div><div class="card-title">Telegram</div>
        <div class="card-sub">${config?.telegram?.enabled ? 'Recibe las alertas en Telegram, aunque no tengas BRASA abierta.' : 'Este servidor aún no tiene un bot de Telegram configurado.'}</div></div>
        <span class="tag ${me.telegram ? 'tag-live' : ''}">${me.telegram ? 'Vinculado' : 'No vinculado'}</span></div>
      <div class="card-actions">${config?.telegram?.enabled ? html`<button class="btn btn-sm" id="ch-telegram">${me.telegram ? 'Volver a vincular' : 'Vincular Telegram'}</button>` : ''}</div>
    </div>
    <div class="btn-row" style="margin-top:14px">
      <button class="btn btn-sm btn-ghost" id="ch-test" ${me.push || me.telegram ? '' : raw('disabled')}>Enviar alerta de prueba</button>
    </div>
    <p class="tiny muted" style="margin-top:12px">BRASA no reemplaza los mensajes de emergencia oficiales que llegan a tu celular (SAE de SENAPRED): mantenlos activos.</p>`, (body) => {
    body.querySelector('#ch-push')?.addEventListener('click', async () => {
      try { await enablePush(config.push.public_key); toast('Notificaciones activadas.'); alertChannels(); } catch (err) { toast(err.message, 'error'); }
    });
    body.querySelector('#ch-push-off')?.addEventListener('click', async () => {
      try { await disablePush(); toast('Avisos desactivados en este teléfono.'); alertChannels(); } catch (err) { toast(err.message, 'error'); }
    });
    body.querySelector('#ch-telegram')?.addEventListener('click', async () => {
      try { const { url } = await api.telegramLink(); window.open(url, '_blank', 'noopener'); toast('Abre el bot y pulsa «Iniciar» para terminar.'); } catch (err) { toast(err.message, 'error'); }
    });
    body.querySelector('#ch-test')?.addEventListener('click', async () => {
      try { const { channels } = await api.testAlert(); toast(channels.length ? `Prueba enviada por: ${channels.join(', ')}.` : 'No se pudo entregar la prueba. Revisa los canales.', channels.length ? 'info' : 'error'); } catch (err) { toast(err.message, 'error'); }
    });
  });
}

// ------------------------------------------------------------------ antibot (Turnstile)
let turnstileScript = null;
/** El script de Turnstile se carga una sola vez, y solo cuando el servidor publica la clave de sitio. */
function ensureTurnstile() {
  if (!turnstileScript) {
    turnstileScript = new Promise((resolve) => {
      const s = document.createElement('script');
      s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
      s.async = true;
      s.onload = () => resolve(window.turnstile);
      s.onerror = () => { turnstileScript = null; resolve(null); }; // si falla, el próximo intento recarga el script
      document.head.appendChild(s);
    });
  }
  return turnstileScript;
}

// ------------------------------------------------------------------ reportes ciudadanos
/* «Tus reportes anteriores» (ALR-16): qué pasó con los que ya envió este dispositivo. Si no hay
   token o la consulta falla, el bloque no se muestra y el formulario funciona igual. */
async function mountMine(body) {
  const host = body.querySelector('#rf-mine');
  if (!host || !storage.get('token')) return;
  try {
    const rows = latest((await request('/api/reports/mine', { auth: true }))?.reports);
    if (!rows.length || !host.isConnected) return;
    host.innerHTML = String(html`<span class="label">Tus reportes anteriores</span>
      <ul class="list">${rows.map((r) => html`<li><span class="grow small ${caducado(r) ? 'muted' : ''}">${line(r)}</span></li>`)}</ul>`);
    host.hidden = false;
  } catch { /* sin bloque: reportar sigue igual */ }
}

/* Cola «sin conexión»: un reporte que no se pudo enviar queda en el teléfono (lo arma reportes.js
   en brasa:outbox) y se reintenta al abrir el formulario y al volver la señal. */

/** Token Turnstile desechable para un reenvío de la cola: el widget del formulario puede no
 *  existir (el reintento también corre con el formulario cerrado). null si no se pudo obtener:
 *  el servidor decide si acepta el reporte igual. */
async function outboxTurnstile() {
  const siteKey = store.get('config')?.turnstile_site_key;
  if (!siteKey) return null;
  const ts = await ensureTurnstile();
  if (!ts) return null;
  return new Promise((resolve) => {
    const host = document.createElement('div');
    host.hidden = true;
    document.body.appendChild(host);
    let settled = false; let widget = null;
    const finish = (token) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try { if (widget != null) ts.remove(widget); } catch { /* el widget ya no existe */ }
      host.remove();
      resolve(token);
    };
    const timer = setTimeout(() => finish(null), 15000);
    try {
      widget = ts.render(host, { sitekey: siteKey, size: 'invisible', callback: finish,
        'error-callback': () => finish(null), 'timeout-callback': () => finish(null) });
      ts.execute(widget);
    } catch { finish(null); }
  });
}

// Mismo límite que el servidor (MAX_UPLOAD_BYTES en backend/reports.py): se avisa
// aquí antes de gastar el antibot y el envío en una foto que va a ser rechazada.
const MAX_UPLOAD = 8 * 1024 * 1024;

/** Baja la foto a un JPEG de lado ≤ 1600 px (FIX-56: lo mismo que hará el servidor,
 *  pero antes de la subida para no gastar la señal en bytes de más). Devuelve el
 *  archivo tal cual si ya es liviano y cabe, o si cualquier paso falla: el envío
 *  sigue igual y el servidor tiene la última palabra. */
async function shrinkPhoto(file) {
  try {
    if (!file.type.startsWith('image/')) return file;
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const dims = fitDimensions(bitmap.width, bitmap.height);
    const fits = dims && dims.width === bitmap.width && dims.height === bitmap.height;
    if (!dims || (fits && !shouldShrink(file))) { bitmap.close(); return file; }
    const canvas = document.createElement('canvas');
    canvas.width = dims.width;
    canvas.height = dims.height;
    canvas.getContext('2d').drawImage(bitmap, 0, 0, dims.width, dims.height);
    bitmap.close();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.82));
    return blob && blob.size < file.size
      ? new File([blob], `${file.name.replace(/\.[^.]+$/, '')}.jpg`, { type: 'image/jpeg' })
      : file;
  } catch { return file; }
}

/** Reenvía los reportes guardados sin señal, del más viejo al más nuevo. 201 (nuevo) y 200 (el
 *  servidor ya tenía uno igual: devuelve `duplicate`) los sacan de la cola; si la señal vuelve a
 *  caer, se detiene y el resto queda para el próximo intento. */
async function flushOutbox() {
  if (navigator.onLine === false) return;
  for (const entry of pendientes()) {
    const form = new FormData();
    form.set('lat', String(entry.lat));
    form.set('lon', String(entry.lon));
    form.set('kind', entry.kind);
    form.set('description', entry.description || '');
    try {
      const token = await outboxTurnstile();
      if (token) form.set('cf-turnstile-response', token);
      await api.createReport(form);
      marcarEnviado(entry.id);
    } catch (err) {
      if (!err.status) break;                      // sin señal otra vez: queda para el próximo intento
      if (err.status === 422) descartar(entry.id); // el dato no sirve (fuera de Chile, tipo inválido): no va a mejorar
    }
  }
}

// Al volver la señal se reenvía lo que quedó guardado.
window.addEventListener('online', () => { flushOutbox(); });

export function reportForm(preset = null, fotoCompartida = null) {
  let point = preset;
  openModal(html`
    <h2 id="modal-title">Reportar humo o fuego</h2>
    <div class="callout callout-urgent small"><b>¿Ves llamas o humo cerca?</b> Llama primero al <a href="tel:130"><b>130</b></a> (CONAF) o al <a href="tel:132"><b>132</b></a> (Bomberos). Este reporte no reemplaza esa llamada.</div>
    <form id="report-form" style="margin-top:14px">
      <div class="field"><span class="label">¿Qué ves?</span>
        <div class="segmented" id="rf-kind">${[['humo', 'Humo'], ['llamas', 'Llamas'], ['quema', 'Quema / fogata'], ['otro', 'Otro']].map(([k, l], i) => html`
          <button type="button" data-kind="${k}" aria-pressed="${i === 0}">${l}</button>`)}</div></div>
      <div class="field"><span class="label">Ubicación aproximada</span>
        <div class="callout small" id="rf-point">${point ? 'Ubicación lista.' : 'Usa tu ubicación o el centro del mapa.'}</div>
        <div class="btn-row" style="margin-top:8px"><button type="button" class="btn btn-sm" id="rf-gps">Estoy aquí ahora</button>
          <button type="button" class="btn btn-sm" id="rf-center">Donde mira el mapa</button></div></div>
      <div class="field"><label for="rf-desc">Descripción (opcional)</label>
        <textarea class="input" id="rf-desc" maxlength="600" placeholder="Ej.: columna de humo blanco hacia el cerro, viento hacia el oriente"></textarea></div>
      <div class="field"><label for="rf-photo">Foto (opcional)</label>
        <input class="input" type="file" id="rf-photo" accept="image/*" capture="environment" />
        <span class="tiny muted" id="rf-photo-size" hidden></span>
        <span class="tiny muted">Borramos de la foto los datos ocultos, como la ubicación guardada por el teléfono.
          Sin conexión se guarda el texto y la ubicación; la foto no.</span></div>
      <p class="tiny muted">Tu reporte lo revisa un voluntario antes de mostrarse. No pedimos tu nombre ni teléfono.</p>
      <div id="rf-turnstile"></div>
      <div class="callout small" id="rf-near" hidden></div>
      <button class="btn btn-primary btn-block" type="submit">Enviar reporte</button>
    </form>
    <div class="field" id="rf-mine" hidden></div>`, (body) => {
    mountMine(body);
    flushOutbox();
    let kind = 'humo';
    // La foto se reduce apenas se elige: el aviso de peso espera el resultado y el
    // submit reutiliza la misma promesa, sin procesar la imagen dos veces.
    const photoInput = body.querySelector('#rf-photo');
    const photoSize = body.querySelector('#rf-photo-size');
    // UX-79: la foto que llegó por «Compartir» no aparece en el control de archivo;
    // `sharedFile` hace las veces de selección hasta que se elija otra a mano.
    let sharedFile = fotoCompartida;
    let photoPromise = null;
    const currentPhoto = () => photoInput.files[0] || sharedFile;
    const showSize = (original) => (shrunk) => {
      if (shrunk !== original && currentPhoto() === original) {
        photoSize.textContent = `La foto se enviará como JPEG de ~${Math.max(1, Math.round(shrunk.size / 1024))} KB.`;
        photoSize.hidden = false;
      }
      return shrunk;
    };
    photoInput.addEventListener('change', () => {
      const file = photoInput.files[0];
      photoSize.hidden = true;
      if (file) sharedFile = null; // la elegida a mano reemplaza a la compartida
      photoPromise = file ? shrinkPhoto(file).then(showSize(file)) : null;
    });
    if (sharedFile) {
      photoSize.textContent = 'La foto que compartiste quedó lista: se envía sin sus datos ocultos.';
      photoSize.hidden = false;
      photoPromise = shrinkPhoto(sharedFile).then(showSize(sharedFile));
    }
    body.querySelectorAll('#rf-kind button').forEach((b) => b.addEventListener('click', () => {
      kind = b.dataset.kind; body.querySelectorAll('#rf-kind button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    }));
    // «Qué ya hay cerca» (REP-01): antes de enviar, avisos de vecinos y puntos de calor del
    // satélite en el mismo punto, solo como contexto. Dos GET públicos en segundo plano; si
    // fallan o llegan tarde, el bloque queda oculto y el envío funciona igual (como mountMine).
    const nearHost = body.querySelector('#rf-near');
    let nearSeq = 0;
    const mountNear = async (p) => {
      const seq = ++nearSeq;
      nearHost.hidden = true; nearHost.innerHTML = '';
      if (!p || !Number.isFinite(p.lat) || !Number.isFinite(p.lon)) return;
      let reports = null; let points = null;
      try { reports = (await api.reports())?.reports; } catch { /* sin datos: no hay bloque */ }
      try {
        const dLat = FOCOS_KM / 110.574;
        const dLon = FOCOS_KM / (111.32 * Math.cos((p.lat * Math.PI) / 180));
        const bbox = `${p.lon - dLon},${p.lat - dLat},${p.lon + dLon},${p.lat + dLat}`;
        points = (await request(`/api/observations?bbox=${bbox}&hours=${FOCOS_HORAS}&reliable=true`))?.points;
      } catch { /* sin datos: no hay bloque */ }
      if (seq !== nearSeq || !nearHost.isConnected) return;
      const near = cercanos(reports, p.lat, p.lon);
      const rows = near.slice(0, 3);
      const focos = resumenFocos(points, p.lat, p.lon);
      if (!rows.length && !focos) return;
      nearHost.innerHTML = String(html`
        ${rows.length ? html`<b class="small">${resumenCercanos(near, p.lat, p.lon)}</b>
        <ul class="list">${rows.map((r) => html`<li><span class="grow small">${distancia(r.km)} · ${line(r)}${testigos(r) ? ` · ${testigos(r)}` : ''}</span></li>`)}</ul>
        <span class="tiny muted" style="display:block">Si es el mismo hecho, avísalo igual: tu reporte ayuda a confirmarlo.</span>` : ''}
        ${focos ? html`<span class="tiny muted" style="display:block">${focos}. Un punto de calor no es un incendio: puede ser una quema, una industria o un falso positivo.</span>` : ''}`);
      nearHost.hidden = false;
    };
    const setPoint = (p) => { point = p; body.querySelector('#rf-point').innerHTML = String(html`<b>Ubicación lista.</b> ${dual('', `${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}`)}`); mountNear(p); };
    if (point) mountNear(point); // el formulario pudo abrir con el punto ya elegido (mapa o ficha)
    body.querySelector('#rf-gps').addEventListener('click', () => navigator.geolocation?.getCurrentPosition(
      (pos) => setPoint({ lat: pos.coords.latitude, lon: pos.coords.longitude }), () => toast('No fue posible obtener tu ubicación.', 'error'), { enableHighAccuracy: true, timeout: 12000 }));
    body.querySelector('#rf-center').addEventListener('click', () => { const c = getMap().getCenter(); setPoint({ lat: c.lat, lon: c.lng }); });
    // Antibot invisible (Turnstile): solo si el servidor publica la clave de sitio. El token va en
    // el campo `cf-turnstile-response` del formulario; si la comprobación no se puede obtener, el
    // reporte se envía igual y la última palabra la tiene el servidor.
    const siteKey = store.get('config')?.turnstile_site_key;
    let turnstileResolve = null; let turnstileReject = null;
    const tryWidget = () => ensureTurnstile().then((ts) => {
      try {
        return ts?.render(body.querySelector('#rf-turnstile'), {
          sitekey: siteKey,
          size: 'invisible',
          callback: (t) => turnstileResolve?.(t),
          'error-callback': () => turnstileReject?.(new Error('antibot')),
          'timeout-callback': () => turnstileReject?.(new Error('antibot')),
        }) ?? null;
      } catch { return null; }
    });
    const widgetReady = siteKey ? tryWidget() : Promise.resolve(null);
    body.querySelector('#report-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!point) return toast('Indica la ubicación del reporte.', 'error');
      const description = body.querySelector('#rf-desc').value;
      const file = currentPhoto();
      // Sin señal el reporte no se pierde: queda en la cola del teléfono y sale al volver la conexión.
      const keepForLater = () => {
        guardar({ kind, lat: point.lat, lon: point.lon, description });
        closeModal();
        toast(`Guardado. Se enviará cuando vuelva la conexión.${file ? ' La foto no se guarda.' : ''}`);
      };
      if (navigator.onLine === false) return keepForLater(); // no gastar el antibot ni el intento
      // La foto viaja ya reducida; si aun así supera 8 MB se avisa aquí, antes del antibot
      // y del envío, en vez de esperar el rechazo del servidor.
      let photo = file;
      if (photo) {
        const shrunk = await (photoPromise || shrinkPhoto(photo));
        photo = currentPhoto() === photo ? shrunk : currentPhoto();
        if (photo.size > MAX_UPLOAD) return toast('La foto supera 8 MB aun después de reducirla. Prueba con otra o recórtala.', 'error');
      }
      const form = new FormData();
      form.set('lat', String(point.lat)); form.set('lon', String(point.lon)); form.set('kind', kind);
      form.set('description', description);
      if (photo) form.set('photo', photo);
      let widget = await Promise.race([widgetReady, new Promise((r) => setTimeout(() => r(null), 3000))]);
      if (widget == null && siteKey) { // la carga pudo fallar al abrir el formulario: un último intento al enviar
        widget = await Promise.race([tryWidget(), new Promise((r) => setTimeout(() => r(null), 3000))]);
      }
      if (widget != null) {
        try {
          const token = await new Promise((resolve, reject) => {
            turnstileResolve = resolve; turnstileReject = reject;
            setTimeout(() => reject(new Error('antibot')), 15000);
            window.turnstile.execute(widget);
          });
          if (token) form.set('cf-turnstile-response', token);
        } catch { /* sin token: el servidor decide si acepta el reporte */ }
      }
      try {
        const res = await api.createReport(form);
        openModal(html`<h2 id="modal-title">Reporte recibido</h2><p>${res.message}</p>${phonesHtml()}
          <div class="field" id="rf-mine" hidden></div>`, mountMine);
      } catch (err) {
        if (!err.status) return keepForLater(); // la señal se cayó en medio del envío
        toast(err.message, 'error');
      }
    });
  });
}

// ------------------------------------------------------------------ ajustes: lectura, letra y tema
const SETTINGS = {
  detail: { label: 'Cómo quieres leer BRASA', options: [['simple', 'Sencilla', 'Palabras simples, lo justo para decidir.'], ['experto', 'Detallada', 'Satélites, sensores, intensidad (FRP), hora UTC y estado de las fuentes.']] },
  text: { label: 'Tamaño de la letra', options: [['normal', 'Normal', ''], ['grande', 'Grande', ''], ['enorme', 'Muy grande', '']] },
  theme: { label: 'Colores', options: [['dark', 'Oscuro', 'Cansa menos la vista de noche.'], ['light', 'Claro', 'Se lee mejor a pleno sol.']] },
};
export function applySetting(key, value) {
  if (key === 'theme') { document.dispatchEvent(new CustomEvent('brasa:theme', { detail: value })); return; }
  document.documentElement.dataset[key] = value;
  storage.set(key, value);
  store.set(key, value);
}
export function openSettings() {
  const current = { detail: document.documentElement.dataset.detail || 'simple', text: document.documentElement.dataset.text || 'normal', theme: store.get('theme') };
  openModal(html`<h2 id="modal-title">Ajustes</h2>
    ${Object.entries(SETTINGS).map(([key, s]) => html`<div class="field"><span class="label">${s.label}</span>
      <div class="option-grid" role="radiogroup" aria-label="${s.label}">${s.options.map(([v, label, hint]) => html`
        <button type="button" class="option ${key === 'text' ? `option-text-${v}` : ''}" role="radio" data-key="${key}" data-value="${v}" aria-checked="${current[key] === v}" tabindex="${current[key] === v ? 0 : -1}">
          <b>${label}</b>${hint ? html`<span>${hint}</span>` : ''}</button>`)}</div></div>`)}
    <div class="field"><span class="label">Batería</span>
      <label class="older-check"><input type="checkbox" id="st-ahorro" ${store.get('ahorro') ? raw('checked') : ''} />
        <span><b>Modo ahorro de batería</b>
          <span class="tiny muted" style="display:block">Menos animaciones y menos actualizaciones. Los avisos siguen llegando.</span></span></label></div>
    ${installGuideFold('Cómo instalar BRASA', 'margin-bottom:14px')}
    <div class="field"><span class="label">Si tu señal es lenta</span>
      <div class="btn-row">
        <a class="btn btn-sm" href="/web/lite.html" data-close>Abrir el modo liviano</a>
      </div>
      <p class="tiny muted">Una página sin mapa, con lo justo: el estado de tus lugares, los últimos avisos y los teléfonos de emergencia. Tus lugares ya están ahí.</p></div>
    <div class="field"><span class="label">Tus datos y privacidad</span>
      <div class="btn-row">
        <a class="btn btn-sm" href="#/privacidad" data-close>Privacidad y términos</a>
        <a class="btn btn-sm" href="/web/estado.html" data-close>Estado del servicio</a>
        <button class="btn btn-sm" type="button" id="st-export">Descargar mis datos</button>
        <button class="btn btn-sm btn-danger" type="button" id="st-delete">Borrar todos mis datos</button>
      </div>
      <p class="tiny muted">BRASA no usa cuentas: todo lo tuyo va con un identificador guardado en este dispositivo. Puedes descargarlo o borrarlo cuando quieras.</p></div>
    <p class="tiny muted">Se guarda en este dispositivo.</p>`, (body) => {
    body.querySelectorAll('[data-close]').forEach((a) => a.addEventListener('click', closeModal));
    body.querySelector('#st-export').addEventListener('click', async () => {
      try {
        const data = await api.exportMe();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
        a.download = `brasa-mis-datos-${new Date().toISOString().slice(0, 10)}.json`;
        a.click(); URL.revokeObjectURL(a.href);
        toast('Descarga lista.');
      } catch (err) { toast(err.message, 'error'); }
    });
    body.querySelector('#st-delete').addEventListener('click', () => {
      openModal(html`<h2 id="modal-title">¿Borrar todos tus datos?</h2>
        <p>Se borran para siempre: tus lugares guardados, su historial de avisos y la suscripción de este dispositivo (push y Telegram). No hay forma de recuperarlos.</p>
        <div class="btn-row" style="margin-top:14px"><button class="btn btn-danger" type="button" id="del-yes">Sí, borrar todo</button>
          <button class="btn btn-ghost" type="button" id="del-no">Cancelar</button></div>`, (b) => {
        b.querySelector('#del-no').addEventListener('click', () => openSettings());
        b.querySelector('#del-yes').addEventListener('click', async () => {
          try {
            await api.deleteMe();
            Object.keys(localStorage).filter((k) => k.startsWith('brasa:')).forEach((k) => localStorage.removeItem(k));
            // El service worker guarda lugares y avisos en caché para verlos sin señal: también se
            // borran, junto con una foto compartida que aún no se haya usado en un reporte (UX-79).
            if ('caches' in window) {
              const keys = await caches.keys();
              await Promise.all(keys.filter((k) => k.endsWith('-api') || k === SHARE_CACHE).map((k) => caches.delete(k)));
            }
            location.hash = '#/mi-zona';
            location.reload();
          } catch (err) { toast(err.message, 'error'); }
        });
      });
    });
    body.querySelector('#st-ahorro').addEventListener('change', (e) => {
      applySetting('ahorro', e.target.checked);
      // El tema oscuro se sugiere, no se impone (UX-76): en pantallas OLED gasta menos.
      if (e.target.checked && store.get('theme') === 'light') {
        toast('Con el tema oscuro la pantalla gasta menos batería.', 'info', 8000,
          { label: 'Usar tema oscuro', onClick: () => applySetting('theme', 'dark') });
      }
    });
    const choose = (b) => {
      applySetting(b.dataset.key, b.dataset.value);
      body.querySelectorAll(`[data-key="${b.dataset.key}"]`).forEach((x) => { x.setAttribute('aria-checked', String(x === b)); x.tabIndex = x === b ? 0 : -1; });
    };
    body.querySelectorAll('[data-key]').forEach((b) => {
      b.addEventListener('click', () => choose(b));
      // Teclado: las flechas mueven la elección dentro del grupo, como en cualquier grupo de opciones.
      b.addEventListener('keydown', (e) => {
        const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        if (!step) return;
        e.preventDefault();
        const group = [...body.querySelectorAll(`[data-key="${b.dataset.key}"]`)];
        const next = group[(group.indexOf(b) + step + group.length) % group.length];
        choose(next); next.focus();
      });
    });
  });
}

// ------------------------------------------------------------------ «Compartir → BRASA» (UX-79)
/* Con la app instalada, la galería del teléfono ofrece BRASA al compartir una foto: el
   manifiesto declara el share_target y el service worker (sw.js) guarda la imagen en una
   caché de un solo uso y abre la app con ?compartir=1. Aquí se recoge la foto y el
   formulario abre ya cargada, por el mismo camino de una foto elegida a mano (shrinkPhoto
   la re-codifica, sin los datos ocultos). En iPhone no se promete: Safari no admite el
   share_target y la entrada jamás llega. */
const SHARE_CACHE = 'brasa-share'; // mismo nombre que en sw.js
const SHARE_KEY = '/__share-foto';

/** La foto que dejó el service worker, como File para el formulario. De un solo uso:
 *  se borra de la caché al tomarla. null si no hay nada o algo falla. */
async function takeSharedPhoto() {
  try {
    const cache = await caches.open(SHARE_CACHE);
    const hit = await cache.match(SHARE_KEY);
    if (!hit) return null;
    await cache.delete(SHARE_KEY);
    const blob = await hit.blob();
    return blob.size && blob.type.startsWith('image/') ? new File([blob], 'foto.jpg', { type: blob.type }) : null;
  } catch { return null; }
}

/** ?compartir=1 en la dirección significa que alguien compartió una foto a BRASA. */
async function openSharedReport() {
  if (!new URLSearchParams(location.search).has('compartir')) return;
  // De un solo uso: una recarga no debe reabrir el formulario ni repetir la foto.
  history.replaceState(null, '', `${location.pathname}${location.hash}`);
  // El antibot del formulario necesita la configuración, que el arranque aún está
  // pidiendo: se espera unos segundos y, si no llega, el formulario abre igual.
  for (let i = 0; i < 12 && !store.get('config'); i += 1) await new Promise((r) => setTimeout(r, 500));
  reportForm(null, await takeSharedPhoto());
}
openSharedReport();
