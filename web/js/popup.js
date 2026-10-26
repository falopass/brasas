/* Un solo detalle a la vez sobre el mapa: el estado vive aquí para que «Mi zona» y el Mapa
 * no queden abiertos a la vez. Bajo 900 px el detalle se acopla abajo (#ficha, MAPA-158);
 * en escritorio sigue siendo el popup flotante de MapLibre. */
import { getMap, setData } from './map.js';
import { enlaceCompartir } from './capas.js';
import { store } from './store.js';
import { openModal, placeForm, reportForm } from './ui.js';
import { enlazarSeguimiento, incidentInfo } from './views/incendio.js';
import { ago, bearingDeg, cardinal, dual, fmtDateTime, fmtNum, fmtUTC, haversineKm, html, SENSOR_LABEL, toast } from './util.js';

// ALR-44: sin sesión el botón «Seguir» lleva al mismo «avisarme» de siempre.
const seguir = (el, sel, target, { lat, lon }) => enlazarSeguimiento(el.querySelector(sel), target, () => { cerrarPopup(); placeForm(null, { lat, lon }); });

// Estado CONAF → etiqueta y tono; la ficha y la lista del Mapa usan las mismas.
export const OFFICIAL_LABEL = { confirmado: 'En curso', controlado: 'Controlado', extinguido: 'Extinguido' };
export const OFFICIAL_TONE = { confirmado: 'urgente', controlado: 'aviso', extinguido: 'tranquilo' };

const EMPTY_SEL = { type: 'FeatureCollection', features: [] };
const par = (l) => (Array.isArray(l) ? l : [l.lng, l.lat]); // LngLat de MapLibre o [lon, lat]
let popup = null;
let fichaPrevSheet = null;   // estado de la hoja antes de que la ficha la bajara a «peek»
let fichaReturnFocus = null; // elemento que la abrió: recupera el foco al cerrar
let escuchas = false;

/** Anillo sobre el punto de la ficha abierta (fuente `seleccion` de map.js). */
function marcarSeleccion(lngLat) {
  setData('seleccion', lngLat
    ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: par(lngLat) }, properties: {} }] }
    : EMPTY_SEL);
}

function ensureEscuchas() {
  if (escuchas) return;
  escuchas = true;
  // Un toque fuera de las capas también cierra lo que esté abierto.
  document.addEventListener('brasa:toque-vacio', cerrarPopup);
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || e.defaultPrevented) return;
    if (document.getElementById('ficha')?.classList.contains('abierta')) cerrarPopup();
  });
  window.addEventListener('resize', () => {
    const el = document.getElementById('ficha');
    if (el?.classList.contains('abierta')) store.set('fichaPx', el.getBoundingClientRect().height);
  });
}

/* #ficha se crea al primer uso (index.html no la declara): diálogo acoplado abajo, con
 * «Cerrar» de 44 px y título que recibe el foco. */
function ensureFicha() {
  let el = document.getElementById('ficha');
  if (el) return el;
  el = document.createElement('div');
  el.id = 'ficha';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-labelledby', 'ficha-titulo');
  el.innerHTML = '<div class="ficha-head"><b class="ficha-titulo" id="ficha-titulo" tabindex="-1"></b>'
    + '<button type="button" class="btn btn-sm" id="ficha-cerrar">Cerrar</button></div>'
    + '<div class="ficha-body"></div>';
  el.querySelector('#ficha-cerrar').addEventListener('click', cerrarPopup);
  document.querySelector('.map-wrap')?.appendChild(el);
  return el;
}

/** La ficha del celular: baja la hoja a «peek», publica su alto (`fichaPx`) y, si el
 *  punto quedó detrás, lo sube al área visible. */
function abrirFicha(lngLat, contenido) {
  const el = ensureFicha();
  const map = getMap();
  if (!el.classList.contains('abierta')) {
    fichaPrevSheet = store.get('sheet');
    document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: 'peek' }));
  }
  fichaReturnFocus = document.activeElement;
  const body = el.querySelector('.ficha-body');
  body.innerHTML = String(contenido);
  el.querySelector('#ficha-titulo').textContent = body.querySelector('b')?.textContent?.trim() || 'Detalle';
  el.classList.add('abierta');
  requestAnimationFrame(() => {
    if (!el.classList.contains('abierta')) return;
    const alto = el.getBoundingClientRect().height;
    store.set('fichaPx', alto);
    const p = map?.project(lngLat);
    if (p && p.y > el.getBoundingClientRect().top - 16) {
      map.easeTo({ center: par(lngLat), padding: { top: 70, bottom: alto + 24, left: 16, right: 16 }, duration: 350 });
    }
  });
  el.querySelector('#ficha-titulo').focus({ preventScroll: true });
  return body;
}

function cerrarFicha() {
  const el = typeof document === 'undefined' ? null : document.getElementById('ficha');
  if (!el?.classList.contains('abierta')) return;
  el.classList.remove('abierta');
  store.set('fichaPx', 0);
  // La hoja vuelve a su estado, salvo que la persona ya la haya movido.
  if (fichaPrevSheet && fichaPrevSheet !== 'peek' && store.get('sheet') === 'peek') {
    document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: fichaPrevSheet }));
  }
  fichaPrevSheet = null;
  if (fichaReturnFocus?.isConnected) fichaReturnFocus.focus({ preventScroll: true });
  fichaReturnFocus = null;
}

/** Abre el único detalle del mapa y devuelve su elemento para atar botones. */
export function abrirPopup(lngLat, contenido, maxWidth = '280px') {
  ensureEscuchas();
  marcarSeleccion(lngLat);
  popup?.remove();
  popup = null;
  if (window.innerWidth < 900) return abrirFicha(lngLat, contenido);
  popup = new maplibregl.Popup({ maxWidth, offset: 10 }).setLngLat(par(lngLat)).setHTML(String(contenido)).addTo(getMap());
  return popup.getElement();
}

export function cerrarPopup() {
  popup?.remove();
  popup = null;
  cerrarFicha();
  marcarSeleccion(null);
}

/** «Compartir» (MAPA-165): navigator.share si existe; si no, modal con WhatsApp y «Copiar enlace». */
export function compartirEnlace(titulo, texto, url) {
  if (navigator.share) {
    navigator.share({ title: titulo, text: texto, url }).catch(() => {});
    return;
  }
  openModal(html`<h2 id="modal-title">Compartir</h2>
    <p class="small muted">${titulo}</p>
    <div class="share-url"><input class="input" id="share-url" readonly value="${url}" aria-label="Enlace para compartir" /></div>
    <div class="btn-row" style="margin-top:10px">
      <a class="btn btn-primary" href="https://wa.me/?text=${encodeURIComponent(texto)}" target="_blank" rel="noopener">Enviar por WhatsApp</a>
      <button class="btn" id="share-copy">Copiar enlace</button></div>`, (body) => {
    body.querySelector('#share-copy').addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(url); toast('Enlace copiado.'); } catch { body.querySelector('#share-url').select(); toast('Selecciona el enlace y cópialo.'); }
    });
  });
}

/** Ficha de un incendio CONAF: la misma desde el punto del mapa y desde la lista. */
export function popupOficial(fire, lngLat) {
  const el = abrirPopup(lngLat, html`<div style="max-width:250px">
    <div class="tiny">Incendio informado por CONAF</div>
    <b>${fire.name || 'Sin nombre'}</b> · <span class="status-badge st-${OFFICIAL_TONE[fire.status]}">${fire.status_raw || OFFICIAL_LABEL[fire.status]}</span>
    <div class="small" style="margin-top:4px">${fire.comuna ? `${fire.comuna}, ${fire.region}` : ''}</div>
    <div class="small">Empezó ${ago(fire.started_at)} · ${fmtDateTime(fire.started_at)}${fire.area_ha ? ` · ${fmtNum(fire.area_ha, fire.area_ha < 10 ? 1 : 0)} ha` : ''}</div>
    <div class="tiny muted" style="margin-top:6px">${dual('Así lo informa CONAF. Sigue a SENAPRED y a tu municipio.', `Fuente: CONAF (GEPRIF), reporte público. Ámbito ${fire.ambito || 'n/d'}${fire.fuel ? ` · combustible inicial: ${fire.fuel}` : ''}.`)}</div>
    <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm btn-ghost" id="pp-follow" aria-pressed="false">Seguir este incendio</button><button class="btn btn-sm" id="pp-share">Compartir</button></div></div>`);
  seguir(el, '#pp-follow', { official_ref: fire.id }, fire);
  el.querySelector('#pp-share').addEventListener('click', () => {
    const url = enlaceCompartir('conaf', fire, location.origin);
    compartirEnlace(`BRASA · ${fire.name || 'Incendio informado por CONAF'}`,
      `CONAF informa el incendio «${fire.name || 'Sin nombre'}» (${fire.status_raw || OFFICIAL_LABEL[fire.status]})${fire.comuna ? ` en ${fire.comuna}` : ''}. Míralo en BRASA: ${url}. Si ves fuego, llama al 130 o al 132.`,
      url);
  });
}

/** Ficha de un incidente (MAPA-163): estado, comuna y cuántas veces se vio calor, con
 *  el enlace a su página. Es la zona donde el satélite vio calor, no el perímetro oficial. */
export function popupIncidente(inc, lngLat) {
  const info = incidentInfo(inc);
  const el = abrirPopup(lngLat, html`<div style="max-width:250px">
    <div class="tiny">Lo que vieron los satélites, agrupado por BRASA</div>
    <b>${info.title}</b> · <span class="status-badge st-${info.tone}">${info.short}</span>
    <div class="small" style="margin-top:4px">${inc.comuna ? `${inc.comuna}, ${inc.region}` : 'En un país vecino'}</div>
    <div class="small">${dual(`Calor visto ${inc.n_obs} ${inc.n_obs === 1 ? 'vez' : 'veces'}`, `${inc.n_obs} detecciones agrupadas`)}${inc.last_seen_at ? ` · la última ${ago(inc.last_seen_at)}` : ''}</div>
    <div class="tiny muted" style="margin-top:6px">${dual('El contorno marca la zona aproximada donde se vio calor: no es el perímetro oficial.', 'Huella aproximada por agrupación espacio-temporal; el perímetro oficial lo fija CONAF.')}</div>
    <div class="btn-row" style="margin-top:10px">
      <a class="btn btn-sm btn-primary" href="#/incendio/${inc.id}">Ver qué ha pasado aquí</a>
      <button class="btn btn-sm btn-ghost" id="pp-follow" aria-pressed="false">Seguir este incendio</button>
      <button class="btn btn-sm" id="pp-share">Compartir</button></div></div>`);
  seguir(el, '#pp-follow', { incident_id: inc.id, official_ref: inc.official_ref || undefined }, inc);
  el.querySelector('#pp-share').addEventListener('click', () => {
    const url = enlaceCompartir('incidente', inc, location.origin);
    compartirEnlace(`BRASA · ${info.title}`,
      `BRASA ve «${info.title}»${inc.comuna ? ` en ${inc.comuna}` : ''}: calor visto ${inc.n_obs} ${inc.n_obs === 1 ? 'vez' : 'veces'}. Mira su ficha: ${url}. Si ves fuego, llama al 130 o al 132.`,
      url);
  });
}

/** Ficha corta de un punto de calor: la comparten el Mapa y «Mi zona». */
export function popupFoco(obs, lngLat) {
  const age = ago(obs.observed_at);
  const reliable = ['alta', 'nominal', 'media'].includes(obs.confidence);
  // El lugar guardado más cercano (< 100 km): orienta sin salir de la ficha.
  const cerca = (store.get('places') || [])
    .map((p) => ({ p, km: haversineKm(p.lat, p.lon, obs.lat, obs.lon) }))
    .filter((x) => x.km < 100)
    .sort((a, b) => a.km - b.km)[0];
  const el = abrirPopup(lngLat, html`<div style="max-width:250px">
    <b>Punto de calor</b> · <span class="muted">visto ${age}</span>
    <div class="small" style="margin-top:4px">${obs.comuna ? `${obs.comuna}, ${obs.region}` : 'Fuera del territorio chileno'}</div>
    ${cerca ? html`<div class="tiny" style="margin-top:4px">A ${fmtNum(cerca.km, cerca.km < 10 ? 1 : 0)} km al ${cardinal(bearingDeg(cerca.p.lat, cerca.p.lon, obs.lat, obs.lon))} de «${cerca.p.name}»</div>` : ''}
    <p class="small x-plain" style="margin:8px 0 0">${obs.sensor === 'ABI' ? 'Lo vio un satélite que mira Chile cada 10 minutos. Marca una zona de unos 2 km: el calor está en algún punto dentro del cuadro.' : 'Lo vio un satélite que pasa sobre Chile unas veces al día. Su ubicación es bastante precisa.'}
      ${reliable ? 'Puede ser un incendio, una quema o una industria.' : 'Es una señal dudosa: puede no ser fuego.'}</p>
    <div class="x-tech small" style="margin-top:6px">
      <div>${SENSOR_LABEL[obs.sensor] || obs.sensor} · <b>${obs.satellite || obs.source}</b></div>
      <div>${fmtDateTime(obs.observed_at)} Chile · ${fmtUTC(obs.observed_at)}</div>
      <div>FRP ${obs.frp_mw != null ? `${fmtNum(obs.frp_mw, 1)} MW` : 'n/d'} · confianza ${obs.confidence || 'n/d'} · ${obs.sensor === 'ABI' ? 'píxel ~2–3 km' : `píxel ${obs.resolution_m || 375} m`}</div>
      <div class="tabular">${obs.lat.toFixed(4)}, ${obs.lon.toFixed(4)}</div></div>
    ${obs.incident_id && obs.incident_n > 1 ? html`<p class="small" style="margin:8px 0 0"><b>${incidentInfo({ status: obs.incident_status, fixed_source: obs.incident_fixed }).title}</b> · ${dual(`se vio calor ${obs.incident_n} veces aquí`, `${obs.incident_n} detecciones agrupadas`)}</p>
      <a class="btn btn-sm btn-primary" style="margin-top:6px" href="#/incendio/${obs.incident_id}">Ver qué ha pasado aquí</a>` : ''}
    <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm" id="pp-watch">Avisarme si hay más aquí</button><button class="btn btn-sm btn-ghost" id="pp-report">Contar lo que veo</button><button class="btn btn-sm btn-ghost" id="pp-share">Compartir</button></div></div>`);
  el.querySelector('#pp-watch').addEventListener('click', () => { cerrarPopup(); placeForm(null, { lat: obs.lat, lon: obs.lon }); });
  el.querySelector('#pp-report').addEventListener('click', () => { cerrarPopup(); reportForm({ lat: obs.lat, lon: obs.lon }); });
  el.querySelector('#pp-share').addEventListener('click', () => {
    const url = enlaceCompartir('foco', obs, location.origin);
    compartirEnlace('BRASA · Punto de calor',
      `Punto de calor visto por satélite ${age}${obs.comuna ? ` en ${obs.comuna}` : ''}. Puede ser un incendio, una quema o una industria. Míralo en BRASA: ${url}. Si ves fuego, llama al 130 (CONAF) o al 132 (Bomberos).`,
      url);
  });
}
