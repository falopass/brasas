/* BRASA Chile — arranque de la aplicación: rutas, navegación, tema, datos compartidos y hoja móvil. */
import { api } from './api.js';
import './instalar.js';
import { detectionsGeoJSON, getMap, initMap, onReady, placesGeoJSON, setData, setTheme } from './map.js';
import { loadObservations, visibleObservations } from './data.js';
import { armEnter, scanPass, watchView } from './motion.js';
import { cachedAge, pillState } from './pildora.js';
import { clearBadge, registerServiceWorker } from './push.js';
import { sondeosMs, store } from './store.js';
import { applySetting, openEmergency, openSettings } from './ui.js';
import { $, ago, debeRecargarVista, storage, toast, yaRecargoSw } from './util.js';
import zona from './views/zona.js';

const ICONS = {
  'mi-zona': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21Z"/><circle cx="12" cy="10" r="2.4"/></svg>',
  mapa: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4Z"/><path d="M9 4v14M15 6v14"/></svg>',
  riesgo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 14.8V5a2 2 0 1 0-4 0v9.8a4 4 0 1 0 4 0Z"/><path d="M12 9v7"/></svg>',
  casos: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
  temporada: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16"/><path d="M8 20v-6M12 20V6M16 20v-10"/></svg>',
  preparate: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.2 7.5 9.5 4.3-1.3 7.5-4.9 7.5-9.5V6L12 3Z"/><path d="m9 12 2 2 4-4"/></svg>',
  alertas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 15V10a6 6 0 1 0-12 0v5l-1.5 2.5h15L18 15Z"/><path d="M10 19.5a2 2 0 0 0 4 0"/></svg>',
  calidad: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2.5 7L14 5l2.5 7H21"/></svg>',
  quehago: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M9.8 9.2a2.3 2.3 0 0 1 4.5.7c0 1.5-2.3 1.9-2.3 3.3"/><path d="M12 16.6v.1"/></svg>',
  mas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="5.5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="18.5" cy="12" r="1.5"/></svg>',
};
// Metadatos livianos para navegar; el módulo de cada vista se pide al entrar.
// `zona` es la portada y viaja en el arranque; las demás se cargan con import()
// y `loadView()` memoriza la promesa para no descargarlas dos veces.
const VIEWS = [
  { id: zona.id, sheet: zona.sheet, load: () => zona },
  { id: 'mapa', sheet: 'peek', load: () => import('./views/mapa.js') },
  { id: 'riesgo', sheet: 'half', load: () => import('./views/riesgo.js') },
  { id: 'alertas', sheet: 'full', load: () => import('./views/alertas.js') },
  { id: 'casos', sheet: 'half', load: () => import('./views/casos.js') },
  { id: 'temporada', sheet: 'full', load: () => import('./views/temporada.js') },
  { id: 'preparate', sheet: 'full', load: () => import('./views/preparate.js') },
  { id: 'calidad', nav: false, sheet: 'full', load: () => import('./views/calidad.js') },
  { id: 'v', nav: false, sheet: 'half', load: () => import('./views/vecino.js') },
  { id: 'incendio', nav: false, sheet: 'half', load: () => import('./views/incendio.js') },
  { id: 'privacidad', nav: false, sheet: 'full', load: () => import('./views/privacidad.js') },
  { id: 'quehago', nav: false, sheet: 'half', load: () => import('./views/quehago.js') },
  { id: 'mas', nav: false, sheet: 'half', load: () => import('./views/mas.js') },
];
const viewPromises = new Map();
function loadView(meta) {
  if (!viewPromises.has(meta.id)) {
    viewPromises.set(meta.id, Promise.resolve(meta.load()).then((mod) => mod.default ?? mod).catch((err) => {
      // Solo recarga si el fallo es de módulos mezclados; un corte offline no debe tirar la pestaña.
      if (debeRecargarVista(err)) setTimeout(() => location.reload(), 300);
      viewPromises.delete(meta.id);
      throw err;
    }));
  }
  return viewPromises.get(meta.id);
}
const LABELS = { 'mi-zona': 'Mi zona', mapa: 'Mapa', riesgo: 'Riesgo', alertas: 'Avisos', casos: 'Historia', temporada: 'Temporada', preparate: 'Prepárate', calidad: 'Calidad', v: 'Lugar compartido', incendio: 'Incidente', privacidad: 'Privacidad', quehago: '¿Qué hago si…?', mas: 'Más' };
// UX-80: en el celular la barra inferior baja a cinco destinos; las secciones que
// salen de ella viven en la vista «Más» y marcan esa pestaña como la activa.
const MAS_VIEWS = new Set(['preparate', 'casos', 'temporada', 'quehago', 'calidad', 'privacidad']);
let current = null;
let lastRoute = '';
// UX-81: la vista real anterior { view, hash }; la ficha del incidente la usa para «← Volver».
let rutaAnterior = { view: null, hash: '' };

function renderNav() {
  // Íconos y etiquetas son constantes de este archivo (contenido confiable).
  const link = (v) => `<a class="nav-link" href="#/${v.id}" data-view="${v.id}">
    <span aria-hidden="true">${ICONS[v.id]}</span><small>${LABELS[v.id]}</small></a>`;
  const rail = VIEWS.filter((v) => v.nav !== false);
  $('#nav').innerHTML = rail.map(link).join('');
  $('#tabbar').innerHTML = rail.slice(0, 4).map(link).join('') + link({ id: 'mas' });
}

function parseRoute() {
  const [path, query = ''] = location.hash.replace(/^#\/?/, '').split('?');
  const [view = 'mi-zona', ...rest] = path.split('/');
  return { view: VIEWS.some((v) => v.id === view) ? view : 'mi-zona', rest, params: Object.fromEntries(new URLSearchParams(query)) };
}

// ------------------------------------------------------------------ motor del mapa diferido
// maplibre-gl.js (~1 MB) no viene en el arranque: lo piden las vistas de mapa, las acciones y, en un momento libre, Mi zona.
const MAP_VIEWS = new Set(['mapa', 'riesgo', 'incendio', 'casos', 'v']);
// PERF-15: cada vista de mapa pide el motor y espera con onReady.
let mapPromise = null;
export function ensureMap() {
  mapPromise ??= new Promise((resolve) => {
    const fail = () => {
      $('#map').innerHTML = '<p class="empty">No se pudo cargar el motor del mapa.</p>';
      mapPromise = null; // la próxima vista o acción que lo pida reintenta la descarga
      resolve(false);
    };
    // MOV-01: el CSS de MapLibre viaja con el motor y va antes de app.css, como en el
    // <head>: si quedara después, sus reglas le ganarían a las de app.css (p. ej. MOV-02).
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = '/web/vendor/maplibre/maplibre-gl.css';
    document.head.insertBefore(css, document.querySelector('link[href="/web/css/app.css"]'));
    const script = document.createElement('script');
    script.src = '/web/vendor/maplibre/maplibre-gl.js';
    script.onload = () => {
      if (!window.maplibregl) return fail();
      let map;
      // Sin WebGL el motor lanza: la vista sigue sin mapa en vez de esperar una promesa que
      // nunca se resuelve (el enlace de familia no cargaba).
      try { map = initMap($('#map')); } catch (err) { console.error('No se pudo iniciar el mapa:', err); return fail(); }
      // Lectura detallada: coordenadas y zoom bajo el cursor, como en un visor SIG.
      const readout = $('#map-readout');
      map.on('mousemove', (e) => { readout.textContent = `${e.lngLat.lat.toFixed(4)}, ${e.lngLat.lng.toFixed(4)} · z ${map.getZoom().toFixed(1)}`; });
      resolve(true);
    };
    script.onerror = fail;
    document.head.appendChild(script);
  });
  return mapPromise;
}

// Mi zona no está en MAP_VIEWS: su motor se pide en un momento libre del navegador.
function ensureMapIdle() {
  const load = () => ensureMap();
  if (window.requestIdleCallback) window.requestIdleCallback(load);
  else setTimeout(load, 1200);
}

// PERF-12: en teléfonos el motor del mapa (~1 MB + WebGL) no se calienta tras el primer
// pintado: espera la primera interacción o ~8 s. En escritorio sigue el reposo.
function calentarMapa(forzar) {
  const tactil = window.matchMedia?.('(pointer: coarse)').matches || navigator.maxTouchPoints > 0;
  if (!forzar && !tactil) return ensureMapIdle();
  let pedido = false;
  const pedir = () => { if (pedido) return; pedido = true; ensureMap(); };
  ['pointerdown', 'keydown'].forEach((ev) => document.addEventListener(ev, pedir, { once: true, passive: true }));
  setTimeout(pedir, 8000);
}

// MOV-01: en Mi zona con ahorro de datos o red lenta el motor (~1 MB) espera el toque
// o ~8 s para no competir con el primer pintado.
function ensureMapTrasPintar() {
  const con = navigator.connection;
  const lenta = Boolean(con && (con.saveData || ['slow-2g', '2g', '3g'].includes(con.effectiveType)));
  return calentarMapa(lenta);
}

// Índice liviano de comunas (nombre, región, centro y caja) para los buscadores y el
// formulario de lugares; PERF-12 lo difiere en teléfonos y se pide en un momento libre.
let indicePedido = false;
function cargarIndiceComunas() {
  if (indicePedido || store.get('comunasIndex')) return;
  indicePedido = true;
  fetch('/web/data/comunas-index.json').then((r) => r.json()).then((index) => {
    store.set('comunasIndex', index.sort((a, b) => a.name.localeCompare(b.name, 'es')));
  }).catch(() => { indicePedido = false; });
}

// Nodo solo para lectores de pantalla: repite el nombre de la vista activa (WCAG 4.1.3).
let liveNote = null;
function announceView(label) {
  if (!liveNote) {
    liveNote = document.createElement('p');
    liveNote.id = 'view-live';
    liveNote.className = 'sr-only';
    liveNote.setAttribute('role', 'status');
    $('#panel').appendChild(liveNote);
  }
  liveNote.textContent = label;
}

// Al navegar, el foco pasa al encabezado de la vista nueva (o a #panel si no hay), sin
// mover el desplazamiento ni robar el foco a quien está escribiendo en un campo (WCAG 2.4.3).
let focusWatch = null;
function focusNewView(container) {
  if ($('#modal').open) return;
  const el = document.activeElement;
  if (el && (el.isContentEditable || el.matches('input, textarea, select'))) return;
  let target = container.querySelector('h1, .view-title') || $('#panel');
  if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
  target.focus({ preventScroll: true });
  // Si el repintado reemplaza el encabezado enfocado, el foco vuelve al nuevo mientras nadie lo tome.
  focusWatch?.disconnect();
  focusWatch = new MutationObserver(() => {
    if (target.isConnected || document.activeElement !== document.body) return;
    const again = container.querySelector('h1, .view-title');
    if (!again) return; // repintado sin encabezado todavía: se reintenta en la siguiente mutación
    target = again;
    target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  });
  focusWatch.observe(container, { childList: true, subtree: true });
}

async function route() {
  // Hash que no es ruta («Saltar al contenido» → #panel): salto de foco, no de vista.
  if (location.hash && !location.hash.startsWith('#/') && current) return;
  const { view, rest, params } = parseRoute();
  const meta = VIEWS.find((v) => v.id === view);
  document.querySelectorAll('.nav-link').forEach((a) => {
    const activa = a.dataset.view === view || (a.dataset.view === 'mas' && MAS_VIEWS.has(view));
    if (activa) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  // La brasa de la barra se desliza hasta la pestaña activa (la posición la usa el CSS).
  const tabs = [...document.querySelectorAll('#tabbar .nav-link')];
  const tabI = tabs.findIndex((a) => a.hasAttribute('aria-current'));
  $('#tabbar').style.setProperty('--tab-i', String(Math.max(0, tabI)));
  $('#tabbar').classList.toggle('sin-activa', tabI < 0);
  const next = await loadView(meta);
  if (current && current !== next) current.unmount?.();
  const container = $('#view');
  const key = `${view}/${rest.join('/')}`;
  const navigated = key !== lastRoute;
  if (navigated) {
    // De dónde se viene de verdad; los repintados de la misma ruta no la tocan.
    if (rutaAnterior.view) store.set('vistaAnterior', rutaAnterior);
    armEnter(); lastRoute = key;
  }
  rutaAnterior = { view, hash: location.hash };
  if (current !== next) { focusWatch?.disconnect(); focusWatch = null; container.replaceChildren(); container.scrollTop = 0;
    $('#map-legend').classList.remove('legend-open', 'legend-closed'); $('#legend-chip')?.setAttribute('aria-expanded', 'false'); }
  current = next;
  store.set('view', view);
  if (view === 'alertas') clearBadge(); // UX-75: leer Avisos limpia el número del ícono
  document.title = `${LABELS[view]} · BRASA Chile`;
  setSheet(next.sheet || 'half');
  if (MAP_VIEWS.has(view)) ensureMap();
  // MOV-01: en Mi zona el motor se pide al quedar libre tras el primer pintado, sin
  // esperar a mount() (un servidor lento no frena la descarga). En red lenta, toque o ~8 s.
  if (view === 'mi-zona') ensureMapTrasPintar();
  await next.mount(container, { rest, params });
  $('#view-skel')?.remove();
  if (!MAP_VIEWS.has(view) && view !== 'mi-zona') calentarMapa();
  // Solo en cambio de vista real (no en repintados de la misma ruta ni si otra navegación ya ganó).
  if (navigated && current === next) { announceView(LABELS[view]); focusNewView(container); }
}

// ------------------------------------------------------------------ tema
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  store.set('theme', theme);
  storage.set('theme', theme);
}

// ------------------------------------------------------------------ hoja deslizable (celular)
const SHEET = { peek: 0.26, half: 0.5, full: 0.9 };
const SHEET_ORDER = ['peek', 'half', 'full'];
let sheetState = 'half';
function setSheet(state) {
  if (!SHEET[state]) return;
  sheetState = state;
  const px = Math.round(SHEET[state] * (window.innerHeight - 64));
  document.documentElement.style.setProperty('--sheet-h', `${px}px`);
  document.documentElement.dataset.sheet = state;
  delete document.documentElement.dataset.sheetAlta;
  // Estado y alto publicados para map.js y popup.js (MAPA-158).
  store.set('sheet', state);
  store.set('sheetPx', px);
}
function setupSheet() {
  const handle = $('#sheet-handle');
  const panel = $('#panel');
  // La caja es fija (94dvh): lo visible llega a la tabbar.
  const altoVisible = () => $('.tabbar').getBoundingClientRect().top - panel.getBoundingClientRect().top;
  let startY = 0; let startH = 0; let dragging = false;
  const mover = (alto) => {
    const h = Math.max(80, Math.min(window.innerHeight * 0.94, alto));
    document.documentElement.style.setProperty('--sheet-h', `${h}px`);
    // A medio arrastre data-sheet aún dice «half»: la hoja alta cede igual (MAPA-169).
    document.documentElement.toggleAttribute('data-sheet-alta', h > window.innerHeight * 0.62);
  };
  // El destino lo fija la dirección del tirón: arriba al estado sobre esa
  // altura, abajo al de abajo — antes «rebotaba» a su posición.
  const soltar = (sube) => {
    const ratio = altoVisible() / (window.innerHeight - 64);
    setSheet(sube
      ? (SHEET_ORDER.find((s) => SHEET[s] > ratio) || 'full')
      : ([...SHEET_ORDER].reverse().find((s) => SHEET[s] < ratio) || 'peek'));
  };
  handle.addEventListener('pointerdown', (e) => {
    dragging = true; startY = e.clientY; startH = altoVisible();
    panel.classList.add('dragging'); handle.setPointerCapture(e.pointerId);
  });
  handle.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    mover(startH + (startY - e.clientY));
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false; panel.classList.remove('dragging');
    const moved = Math.abs(e.clientY - startY) > 6;
    if (!moved) return setSheet(sheetState === 'full' ? 'peek' : sheetState === 'peek' ? 'half' : 'full');
    soltar(e.clientY < startY);
  };
  handle.addEventListener('pointerup', end);
  handle.addEventListener('pointercancel', end);
  handle.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSheet(sheetState === 'full' ? 'peek' : sheetState === 'peek' ? 'half' : 'full'); }
  });
  // La hoja también se mueve desde su contenido, como en cualquier mapa del celular: con
  // la hoja baja, tirar hacia arriba la abre antes de desplazar el texto; con el texto en
  // su inicio, tirar hacia abajo la baja. Un gesto horizontal (chips, gráficos) no la mueve.
  const cuerpo = $('#view');
  let t0 = null; let modo = '';
  cuerpo.addEventListener('touchstart', (e) => {
    t0 = e.touches.length === 1 && getComputedStyle(handle).display !== 'none' ? e.touches[0] : null;
    modo = ''; startH = altoVisible();
  }, { passive: true });
  cuerpo.addEventListener('touchmove', (e) => {
    if (!t0) return;
    const dx = e.touches[0].clientX - t0.clientX; const dy = e.touches[0].clientY - t0.clientY;
    if (!modo) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      const vertical = Math.abs(dy) > Math.abs(dx);
      modo = vertical && (dy < 0 ? sheetState !== 'full' : cuerpo.scrollTop <= 0) ? 'hoja' : 'texto';
      if (modo === 'hoja') panel.classList.add('dragging');
    }
    if (modo !== 'hoja') return;
    e.preventDefault();
    mover(startH - dy);
  }, { passive: false });
  const finToque = (e) => {
    if (modo !== 'hoja') return;
    modo = ''; panel.classList.remove('dragging');
    soltar(e.changedTouches[0].clientY < t0.clientY);
  };
  cuerpo.addEventListener('touchend', finToque);
  cuerpo.addEventListener('touchcancel', finToque);
  document.addEventListener('brasa:sheet', (e) => setSheet(e.detail));
  window.addEventListener('resize', () => setSheet(sheetState));
}

// En celular la leyenda se repliega en un chip: el mapa queda libre y la tarjeta se
// despliega solo al tocarla. La visibilidad del chip es CSS puro (mobile-show + :empty);
// aquí solo va el toggle. Al cambiar de vista, route() retira legend-open.
function setupLegendChip() {
  const legend = $('#map-legend');
  const chip = $('#legend-chip');
  if (!legend || !chip) return;
  chip.addEventListener('click', () => {
    const open = legend.classList.toggle('legend-open');
    // Una sola capa abierta a la vez: si la leyenda se despliega, «Capas» y «Filtros» se pliegan.
    if (open) { legend.classList.remove('legend-closed'); legend.querySelector('.legend-fold')?.setAttribute('aria-expanded', 'true'); const capas = $('#map-layers'); if (capas) capas.open = false; const filtros = $('#map-filters'); if (filtros) filtros.open = false; }
    chip.setAttribute('aria-expanded', String(open));
  });
}

// ------------------------------------------------------------------ datos compartidos
// Exportadas: el «Actualizar» del mapa (refresco.js) corre una vuelta a mano con ellas.
export async function refreshObservations() {
  try {
    const data = await loadObservations();
    store.set('obsError', null);
    if (!data) return;
    const before = store.get('observations');
    const newest = (pts) => (pts || []).reduce((m, o) => (o.observed_at > m ? o.observed_at : m), '');
    // Una pasada de barrido sobre el mapa al cargar y cada vez que entra una detección más reciente.
    if (!before || newest(data.points) > newest(before)) setTimeout(scanPass, before ? 0 : 900);
    store.set('observations', data.points);
  } catch (err) {
    // Guardado al modo de statusError: el «Actualizar» manual avisa con el detalle.
    store.set('obsError', err);
    if (err.code === 'OFFLINE') store.set('online', false);
  }
}
export async function refreshStatus() {
  try {
    store.set('status', await api.status());
    store.set('statusError', null);
    store.set('online', true);
  } catch (err) {
    // El error se guarda tal cual: un 5xx no apaga la señal del teléfono — el que falla es BRASA.
    store.set('statusError', err);
    store.set('online', navigator.onLine !== false && err?.code !== 'OFFLINE' && err?.code !== 'TIMEOUT');
  }
  updateLivePill();
}
export async function refreshPlaces() {
  try { store.set('places', (await api.places()).places); } catch { store.set('places', []); }
  store.set('placesReady', true); // PERF-13: desde aquí la portada ya sabe si hay lugares
}

function updateLivePill() {
  const pill = $('#live-pill');
  const status = store.get('status');
  const p = pillState({
    online: store.get('online'),
    statusError: store.get('statusError'),
    status,
    cachedAt: storage.get('cached-at'),
  });
  // FUEGO-08: cuando la frescura por fuente marca una fuente concreta atrasada, la píldora la
  // nombra («Sin datos nuevos de FIRMS hace 2 h») en vez de la frase genérica.
  const products = status?.freshness?.products;
  if (p.state === 'stale' && products) {
    const atrasadas = Object.entries(products).filter(([, f]) => f.stale);
    if (atrasadas.length) {
      const [nombre, info] = atrasadas.sort((a, b) => (b[1].age_seconds ?? Infinity) - (a[1].age_seconds ?? Infinity))[0];
      const cuando = info.age_seconds == null ? '' : ` ${ago(new Date(Date.now() - info.age_seconds * 1000).toISOString())}`;
      p.text = `Sin datos nuevos de ${nombre}${cuando}`;
      p.short = `${nombre} atrasada`;
    }
  }
  pill.dataset.state = p.state;
  pill.setAttribute('aria-live', 'polite');  // que el cambio de estado se anuncie, no solo se pinte
  $('#live-text').textContent = p.text;
  $('#live-short').textContent = p.short;
  pill.title = p.title;
}

function paintSharedLayers() {
  const { dots, blobs } = detectionsGeoJSON(visibleObservations());
  setData('detections', dots);
  setData('goes-pixels', blobs);
  // /v muestra el lugar compartido, no el del visitante.
  if (store.get('view') === 'v') return;
  const { points, radius } = placesGeoJSON(store.get('places') || []);
  setData('places', points);
  setData('place-radius', radius);
}

async function main() {
  renderNav();
  watchView($('#view'));
  applyTheme(document.documentElement.dataset.theme || 'dark');
  store.set('ahorro', storage.get('ahorro') === true);
  setupSheet();
  setupLegendChip();
  ['#settings-btn', '#settings-btn-m'].forEach((sel) => $(sel)?.addEventListener('click', openSettings));
  document.addEventListener('brasa:theme', (e) => { if (e.detail !== store.get('theme')) { applyTheme(e.detail); setTheme(e.detail); } });
  $('#emergency-btn')?.addEventListener('click', openEmergency);
  $('#live-pill')?.addEventListener('click', () => { location.hash = '#/calidad'; });
  // El motor del mapa (~1 MB) corre en paralelo a la conexión en vez de esperarla.
  // MOV-01: en Mi zona (la portada) no compite con el primer pintado: lo pide
  // ensureMapTrasPintar() al montar la vista.
  const entrada = parseRoute();
  if (MAP_VIEWS.has(entrada.view)) ensureMap();
  // El índice de comunas no depende del motor (diferido en teléfonos): los buscadores lo necesitan.
  if (window.requestIdleCallback) window.requestIdleCallback(cargarIndiceComunas, { timeout: 4000 });
  else setTimeout(cargarIndiceComunas, 1200);
  window.addEventListener('online', () => { store.set('online', true); refreshStatus(); });
  window.addEventListener('offline', () => {
    store.set('online', false);
    updateLivePill();
    const age = cachedAge(storage.get('cached-at'));
    toast(age ? `Sin conexión: se muestran datos de ${age}.` : 'Sin conexión: se muestran los últimos datos guardados.', 'error');
  });

  // Con la configuración guardada la vista monta sin esperarla; la fresca llega después.
  // En Cloudflare el backend puede estar despertando (503): se reintenta antes de rendirse.
  const copia = storage.get('config');
  if (copia) store.set('config', copia);
  const pedirConfig = async () => {
    for (let attempt = 0; attempt < 8; attempt++) {
      try {
        store.set('config', await api.config());
        storage.set('config', store.get('config'));
        break;
      } catch (err) {
        if (copia) break;
        if (err.status === 503 && attempt < 7) {
          $('#live-text').textContent = 'Conectando con BRASA…';
          $('#live-short').textContent = 'Conectando…';
          await new Promise((resolve) => setTimeout(resolve, 2500));
          continue;
        }
        toast(`No se pudo conectar con el servidor de BRASA: ${err.message}`, 'error', 8000);
        break;
      }
    }
  };
  if (copia) pedirConfig(); else await pedirConfig();
  // Acciones que usan el mapa fuera de las vistas de mapa: el clic espera al motor y se
  // reintenta; sin él no harían nada.
  document.addEventListener('click', (e) => {
    if (getMap()) return;
    const btn = e.target.closest?.('#pf-map, [data-act="ver"], [data-alert-lat]');
    if (!btn) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    toast('Cargando el mapa…', 'info', 10000);
    ensureMap().then((ok) => { if (ok) btn.click(); else toast('No se pudo cargar el motor del mapa.', 'error'); });
  }, true);

  store.on('observations', paintSharedLayers);
  store.on('places', paintSharedLayers);
  store.on('obsFilter', paintSharedLayers);
  store.on('online', updateLivePill);
  onReady(paintSharedLayers);
  store.on('theme', () => onReady(paintSharedLayers));
  document.addEventListener('brasa:places-changed', refreshPlaces);

  window.addEventListener('hashchange', route);
  // Las tres cargas iniciales no bloquean el montaje: las vistas se suscriben al store
  // y se repintan cuando cada dato llega (los refresh* guardan su error, nunca rechazan).
  const iniciales = Promise.all([refreshPlaces(), refreshObservations(), refreshStatus()]);
  await route();
  // MOV-01 (atajo de MOV-03): #/mi-zona?cerca=1 abre «¿Hay fuego cerca de ti?» una sola
  // vez; el parámetro se quita para que una recarga no la reabra.
  if (entrada.view === 'mi-zona' && entrada.params.cerca === '1') {
    history.replaceState(null, '', '#/mi-zona');
    import('./cerca.js').then((m) => m.abrirCerca());
  }
  await iniciales;
  // Con la pestaña oculta los sondeos se saltan la solicitud: no se gasta batería ni datos.
  // El modo ahorro (UX-76) los espacia: el reloj relee la preferencia en cada vuelta.
  const sondear = (fn, clave) => {
    const vuelta = () => {
      if (!document.hidden) fn();
      setTimeout(vuelta, sondeosMs(store.get('ahorro'))[clave]);
    };
    setTimeout(vuelta, sondeosMs(store.get('ahorro'))[clave]);
  };
  sondear(refreshObservations, 'observations');
  sondear(refreshStatus, 'status');
  sondear(updateLivePill, 'pill');
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    refreshStatus();
    refreshObservations();
    updateLivePill();
  });
  // UX-76: con poca batería y sin cargar se sugiere el modo ahorro, una vez por sesión; nunca solo.
  if (navigator.getBattery) {
    navigator.getBattery().then((b) => {
      if (b.charging || b.level >= 0.2 || store.get('ahorro')) return;
      toast('Queda poca batería: activa el modo ahorro para que el teléfono dure más.', 'info', 12000,
        { label: 'Activar', onClick: () => applySetting('ahorro', true) });
    }).catch(() => {});
  }
  registerServiceWorker(() => {
    const avisarActualizar = () => toast('Hay una versión nueva de BRASA.', 'info', 60000, { label: 'Actualizar', onClick: () => location.reload() });
    // Un service worker nuevo ya trae la versión coherente: una sola recarga por pestaña evita quedar con módulos viejos, pero no con un diálogo abierto (un reporte perdería su borrador).
    if (!document.getElementById('modal')?.open && !yaRecargoSw()) { location.reload(); return; }
    avisarActualizar();
  });
}

main().catch((err) => {
  // Un error de arranque no debe dejar la pantalla vacía: los números de emergencia siempre quedan a mano.
  console.error(err);
  toast('Algo falló al abrir BRASA. Recarga la página. En una emergencia llama al 130 o al 132.', 'error', 15000);
});
