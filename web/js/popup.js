/* Un solo detalle a la vez sobre el mapa, en cualquier vista: el estado vive aquí para
 * que la ficha del punto de calor en «Mi zona» y los popups del Mapa no queden abiertos
 * a la vez ni se borren entre sí. Bajo 900 px el detalle se acopla abajo (#ficha,
 * MAPA-158): un diálogo sobre la barra que la hoja no tapa; en escritorio sigue siendo
 * el popup flotante de MapLibre de siempre. */
import { getMap, setData } from './map.js';
import { store } from './store.js';
import { placeForm, reportForm } from './ui.js';
import { incidentInfo } from './views/incendio.js';
import { ago, bearingDeg, cardinal, dual, fmtDateTime, fmtNum, fmtUTC, haversineKm, html, SENSOR_LABEL } from './util.js';

// Estado de un incendio CONAF → etiqueta corta y tono de insignia; la ficha y la
// lista del Mapa usan las mismas, por eso viven aquí y no en la vista.
export const OFFICIAL_LABEL = { confirmado: 'En curso', controlado: 'Controlado', extinguido: 'Extinguido' };
export const OFFICIAL_TONE = { confirmado: 'urgente', controlado: 'aviso', extinguido: 'tranquilo' };

const EMPTY_SEL = { type: 'FeatureCollection', features: [] };
const par = (l) => (Array.isArray(l) ? l : [l.lng, l.lat]); // LngLat de MapLibre o [lon, lat]
let popup = null;
let fichaPrevSheet = null;   // estado de la hoja antes de que la ficha la bajara a «peek»
let fichaReturnFocus = null; // elemento que la abrió: recupera el foco al cerrar
let escuchas = false;

/** Anillo sobre el punto cuya ficha está abierta (la fuente `seleccion` de map.js). */
function marcarSeleccion(lngLat) {
  setData('seleccion', lngLat
    ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: par(lngLat) }, properties: {} }] }
    : EMPTY_SEL);
}

function ensureEscuchas() {
  if (escuchas) return;
  escuchas = true;
  // Un toque en un lugar sin capas registradas también cierra lo que esté abierto.
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

/* #ficha se crea la primera vez que se usa (index.html no la declara): diálogo acoplado
 * abajo en el celular, con su «Cerrar» de 44 px y título que recibe el foco al abrir. */
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

/** La ficha del celular: baja la hoja a «peek», publica su alto (`fichaPx`) para que
 *  el mapa se acolche y, si el punto quedó detrás de ella, lo sube al área visible. */
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
  // La hoja vuelve al estado que tenía, salvo que la persona ya la haya movido.
  if (fichaPrevSheet && fichaPrevSheet !== 'peek' && store.get('sheet') === 'peek') {
    document.dispatchEvent(new CustomEvent('brasa:sheet', { detail: fichaPrevSheet }));
  }
  fichaPrevSheet = null;
  if (fichaReturnFocus?.isConnected) fichaReturnFocus.focus({ preventScroll: true });
  fichaReturnFocus = null;
}

/** Abre el único detalle del mapa (cierra el anterior) y devuelve su elemento para atar botones. */
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

/** Ficha de un incendio informado por CONAF: la misma desde el punto del mapa y desde la lista. */
export function popupOficial(fire, lngLat) {
  abrirPopup(lngLat, html`<div style="max-width:250px">
    <div class="tiny">Incendio informado por CONAF</div>
    <b>${fire.name || 'Sin nombre'}</b> · <span class="status-badge st-${OFFICIAL_TONE[fire.status]}">${fire.status_raw || OFFICIAL_LABEL[fire.status]}</span>
    <div class="small" style="margin-top:4px">${fire.comuna ? `${fire.comuna}, ${fire.region}` : ''}</div>
    <div class="small">Empezó ${ago(fire.started_at)} · ${fmtDateTime(fire.started_at)}${fire.area_ha ? ` · ${fmtNum(fire.area_ha, fire.area_ha < 10 ? 1 : 0)} ha` : ''}</div>
    <div class="tiny muted" style="margin-top:6px">${dual('Así lo informa CONAF. Sigue a SENAPRED y a tu municipio.', `Fuente: CONAF (GEPRIF), reporte público. Ámbito ${fire.ambito || 'n/d'}${fire.fuel ? ` · combustible inicial: ${fire.fuel}` : ''}.`)}</div></div>`);
}

/** Ficha corta de un punto de calor: la misma que abre el Mapa; «Mi zona» la comparte. */
export function popupFoco(obs, lngLat) {
  const age = ago(obs.observed_at);
  const reliable = ['alta', 'nominal', 'media'].includes(obs.confidence);
  // El lugar guardado más cercano, si está a menos de 100 km: orienta sin salir de la ficha.
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
    <div class="btn-row" style="margin-top:10px"><button class="btn btn-sm" id="pp-watch">Avisarme si hay más aquí</button><button class="btn btn-sm btn-ghost" id="pp-report">Contar lo que veo</button></div></div>`);
  el.querySelector('#pp-watch').addEventListener('click', () => { cerrarPopup(); placeForm(null, { lat: obs.lat, lon: obs.lon }); });
  el.querySelector('#pp-report').addEventListener('click', () => { cerrarPopup(); reportForm({ lat: obs.lat, lon: obs.lon }); });
}
