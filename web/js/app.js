/* BRASA Chile — arranque de la aplicación: rutas, navegación, tema, datos compartidos y hoja móvil. */
import { api } from './api.js';
import { detectionsGeoJSON, getMap, initMap, onReady, placesGeoJSON, setData, setTheme } from './map.js';
import { loadObservations, visibleObservations } from './data.js';
import { armEnter, scanPass, watchView } from './motion.js';
import { cachedAge, pillState } from './pildora.js';
import { clearBadge, registerServiceWorker } from './push.js';
import { sondeosMs, store } from './store.js';
import { applySetting, openEmergency, openSettings } from './ui.js';
import { $, ago, storage, toast } from './util.js';
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
    viewPromises.set(meta.id, Promise.resolve(meta.load()).then((mod) => mod.default ?? mod));
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
// maplibre-gl.js (~1 MB) no viene en el arranque: se inyecta cuando una vista dibuja o
// encuadra en el mapa, cuando una acción lo pide (marcar un lugar, «ver en el mapa») o en
// un momento libre tras montar otra vista, porque Mi zona (la portada) dibuja sus lugares.
const MAP_VIEWS = new Set(['mapa', 'riesgo', 'incendio', 'casos', 'v']);
let mapPromise = null;
function ensureMap() {
  mapPromise ??= new Promise((resolve) => {
    const fail = () => {
      $('#map').innerHTML = '<p class="empty">No se pudo cargar el motor del mapa.</p>';
      mapPromise = null; // la próxima vista o acción que lo pida reintenta la descarga
      resolve(false);
    };
    const script = document.createElement('script');
    script.src = '/web/vendor/maplibre/maplibre-gl.js';
    script.onload = () => {
      if (!window.maplibregl) return fail();
      const map = initMap($('#map'));
      // Lectura detallada: coordenadas y zoom bajo el cursor, como en un visor SIG.
      const readout = $('#map-readout');
      map.on('mousemove', (e) => { readout.textContent = `${e.lngLat.lat.toFixed(4)}, ${e.lngLat.lng.toFixed(4)} · z ${map.getZoom().toFixed(1)}`; });
      // Índice liviano de comunas para los buscadores (nombre, región, centro y caja); el mapa carga el geojson aparte.
      fetch('/web/data/comunas-index.json').then((r) => r.json()).then((index) => {
        store.set('comunasIndex', index.sort((a, b) => a.name.localeCompare(b.name, 'es')));
      }).catch(() => {});
      resolve(true);
    };
    script.onerror = fail;
    document.head.appendChild(script);
  });
  return mapPromise;
}

// Mi zona (la portada) no está en MAP_VIEWS para no esperar la descarga en su mount; el
// motor se pide igual, en un momento libre del navegador.
function ensureMapIdle() {
  const load = () => ensureMap();
  if (window.requestIdleCallback) window.requestIdleCallback(load);
  else setTimeout(load, 1200);
}

// Nodo solo para lectores de pantalla: repite el nombre de la vista activa dentro de
// #panel (ya aria-live="polite"), para que el cambio de sección se anuncie (WCAG 4.1.3).
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
  // Las vistas se repintan cuando llegan datos nuevos: si el encabezado enfocado se
  // reemplaza, el foco vuelve al nuevo mientras nadie lo haya tomado.
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
  // Un hash que no es ruta («Saltar al contenido» apunta a #panel) es un salto de foco, no de vista.
  if (location.hash && !location.hash.startsWith('#/') && current) return;
  const { view, rest, params } = parseRoute();
  const meta = VIEWS.find((v) => v.id === view);
  document.querySelectorAll('.nav-link').forEach((a) => {
    const activa = a.dataset.view === view || (a.dataset.view === 'mas' && MAS_VIEWS.has(view));
    if (activa) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
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
    $('#map-legend').classList.remove('legend-open'); $('#legend-chip')?.setAttribute('aria-expanded', 'false'); }
  current = next;
  store.set('view', view);
  if (view === 'alertas') clearBadge(); // UX-75: leer Avisos limpia el número del ícono
  document.title = `${LABELS[view]} · BRASA Chile`;
  setSheet(next.sheet || 'half');
  if (MAP_VIEWS.has(view)) await ensureMap();
  await next.mount(container, { rest, params });
  if (!MAP_VIEWS.has(view)) ensureMapIdle();
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
const SHEET = { peek: 0.24, half: 0.5, full: 0.9 };
let sheetState = 'half';
function setSheet(state) {
  if (!SHEET[state]) return;
  sheetState = state;
  const px = Math.round(SHEET[state] * (window.innerHeight - 64));
  document.documentElement.style.setProperty('--sheet-h', `${px}px`);
  // Estado y alto publicados (MAPA-158): map.js acolcha la cámara con ellos y
  // popup.js recuerda a cuál volver al cerrar la ficha. Se leen del store, no del panel.
  store.set('sheet', state);
  store.set('sheetPx', px);
}
function setupSheet() {
  const handle = $('#sheet-handle');
  const panel = $('#panel');
  let startY = 0; let startH = 0; let dragging = false;
  handle.addEventListener('pointerdown', (e) => {
    dragging = true; startY = e.clientY; startH = panel.getBoundingClientRect().height;
    panel.classList.add('dragging'); handle.setPointerCapture(e.pointerId);
  });
  handle.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const h = Math.max(80, Math.min(window.innerHeight * 0.94, startH + (startY - e.clientY)));
    document.documentElement.style.setProperty('--sheet-h', `${h}px`);
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false; panel.classList.remove('dragging');
    const ratio = panel.getBoundingClientRect().height / (window.innerHeight - 64);
    const moved = Math.abs(e.clientY - startY) > 6;
    if (!moved) return setSheet(sheetState === 'full' ? 'peek' : sheetState === 'peek' ? 'half' : 'full');
    setSheet(ratio > 0.7 ? 'full' : ratio > 0.36 ? 'half' : 'peek');
  };
  handle.addEventListener('pointerup', end);
  handle.addEventListener('pointercancel', end);
  handle.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSheet(sheetState === 'full' ? 'peek' : sheetState === 'peek' ? 'half' : 'full'); }
  });
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
    chip.setAttribute('aria-expanded', String(open));
  });
}

// ------------------------------------------------------------------ datos compartidos
async function refreshObservations() {
  try {
    const data = await loadObservations();
    if (!data) return;
    const before = store.get('observations');
    const newest = (pts) => (pts || []).reduce((m, o) => (o.observed_at > m ? o.observed_at : m), '');
    // Una pasada de barrido sobre el mapa al cargar y cada vez que entra una detección más reciente.
    if (!before || newest(data.points) > newest(before)) setTimeout(scanPass, before ? 0 : 900);
    store.set('observations', data.points);
  } catch (err) {
    if (err.code === 'OFFLINE') store.set('online', false);
  }
}
async function refreshStatus() {
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
  const { dots, squares } = detectionsGeoJSON(visibleObservations());
  setData('detections', dots);
  setData('goes-pixels', squares);
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
  window.addEventListener('online', () => { store.set('online', true); refreshStatus(); });
  window.addEventListener('offline', () => {
    store.set('online', false);
    updateLivePill();
    const age = cachedAge(storage.get('cached-at'));
    toast(age ? `Sin conexión: se muestran datos de ${age}.` : 'Sin conexión: se muestran los últimos datos guardados.', 'error');
  });

  // En Cloudflare el backend puede estar despertando (503): se reintenta unos segundos antes de rendirse.
  for (let attempt = 0; attempt < 8; attempt++) {
    try {
      store.set('config', await api.config());
      break;
    } catch (err) {
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
  // Acciones que usan el mapa fuera de las vistas de mapa (marcar un lugar, «ver en el mapa»):
  // el clic espera la descarga del motor y se reintenta; sin el mapa, no harían nada o caerían.
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
  await Promise.all([refreshPlaces(), refreshObservations(), refreshStatus()]);
  await route();
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
  registerServiceWorker(() => toast('Hay una versión nueva de BRASA.', 'info', 60000, { label: 'Actualizar', onClick: () => location.reload() }));
}

main().catch((err) => {
  // Un error de arranque no debe dejar la pantalla vacía: los números de emergencia siempre quedan a mano.
  console.error(err);
  toast('Algo falló al abrir BRASA. Recarga la página. En una emergencia llama al 130 o al 132.', 'error', 15000);
});
