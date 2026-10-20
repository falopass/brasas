/* BRASA Chile — arranque de la aplicación: rutas, navegación, tema, datos compartidos y hoja móvil. */
import { api } from './api.js';
import { detectionsGeoJSON, getMap, initMap, onReady, placesGeoJSON, setData, setTheme } from './map.js';
import { loadObservations, visibleObservations } from './data.js';
import { armEnter, scanPass, watchView } from './motion.js';
import { registerServiceWorker } from './push.js';
import { store } from './store.js';
import { openEmergency, openSettings } from './ui.js';
import { $, ago, minutesSince, storage, toast } from './util.js';
import zona from './views/zona.js';
import mapa from './views/mapa.js';
import riesgo from './views/riesgo.js';
import alertas from './views/alertas.js';
import casos from './views/casos.js';
import temporada from './views/temporada.js';
import preparate from './views/preparate.js';
import vecino from './views/vecino.js';
import incendio from './views/incendio.js';
import privacidad from './views/privacidad.js';
import calidad from './views/calidad.js';
import quehago from './views/quehago.js';

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
};
const VIEWS = [zona, mapa, riesgo, alertas, casos, temporada, preparate, calidad, vecino, incendio, privacidad, quehago];
const LABELS = { 'mi-zona': 'Mi zona', mapa: 'Mapa', riesgo: 'Riesgo', alertas: 'Avisos', casos: 'Historia', temporada: 'Temporada', preparate: 'Prepárate', calidad: 'Calidad', v: 'Lugar compartido', incendio: 'Incidente', privacidad: 'Privacidad', quehago: '¿Qué hago si…?' };
let current = null;
let lastRoute = '';

function renderNav() {
  // Íconos y etiquetas son constantes de este archivo (contenido confiable).
  const markup = VIEWS.filter((v) => v.nav !== false).map((v) => `<a class="nav-link" href="#/${v.id}" data-view="${v.id}">
    <span aria-hidden="true">${ICONS[v.id]}</span><small>${LABELS[v.id]}</small></a>`).join('');
  $('#nav').innerHTML = markup;
  $('#tabbar').innerHTML = markup;
}

function parseRoute() {
  const [path, query = ''] = location.hash.replace(/^#\/?/, '').split('?');
  const [view = 'mi-zona', ...rest] = path.split('/');
  return { view: VIEWS.some((v) => v.id === view) ? view : 'mi-zona', rest, params: Object.fromEntries(new URLSearchParams(query)) };
}

// ------------------------------------------------------------------ motor del mapa diferido
// maplibre-gl.js (~1 MB) no viene en el arranque: se inyecta solo cuando una vista dibuja o
// encuadra en el mapa, o cuando una acción lo pide (marcar un lugar, «ver en el mapa»).
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
function focusNewView(container) {
  const el = document.activeElement;
  if (el && (el.isContentEditable || el.matches('input, textarea, select'))) return;
  const target = container.querySelector('h1, .view-title') || $('#panel');
  if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
  target.focus({ preventScroll: true });
}

async function route() {
  // Un hash que no es ruta («Saltar al contenido» apunta a #panel) es un salto de foco, no de vista.
  if (location.hash && !location.hash.startsWith('#/') && current) return;
  const { view, rest, params } = parseRoute();
  const next = VIEWS.find((v) => v.id === view);
  document.querySelectorAll('.nav-link').forEach((a) => { if (a.dataset.view !== view) a.removeAttribute('aria-current'); else a.setAttribute('aria-current', 'page'); });
  if (current && current !== next) current.unmount?.();
  const container = $('#view');
  const key = `${view}/${rest.join('/')}`;
  const navigated = key !== lastRoute;
  if (navigated) { armEnter(); lastRoute = key; }
  if (current !== next) { container.replaceChildren(); container.scrollTop = 0; }
  current = next;
  store.set('view', view);
  document.title = `${LABELS[view]} · BRASA Chile`;
  setSheet(next.sheet || 'half');
  if (MAP_VIEWS.has(view)) await ensureMap();
  await next.mount(container, { rest, params });
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
  sheetState = state;
  document.documentElement.style.setProperty('--sheet-h', `${Math.round(SHEET[state] * (window.innerHeight - 64))}px`);
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
  try { store.set('status', await api.status()); store.set('online', true); } catch { store.set('online', false); }
  updateLivePill();
}
export async function refreshPlaces() {
  try { store.set('places', (await api.places()).places); } catch { store.set('places', []); }
}

/** Edad del último /api/status que sirvió la caché del service worker («hace 5 min», «hace 2 h») o null. */
function cachedAge() {
  const at = storage.get('cached-at');
  const min = minutesSince(at);
  if (!Number.isFinite(min)) return null;
  return min < 60 ? `hace ${Math.round(min)} min` : ago(at);
}

function updateLivePill() {
  const pill = $('#live-pill');
  const status = store.get('status');
  const newest = status ? Object.values(status.newest_observation || {}).sort().pop() : null;
  const lastIngest = status?.last_ingest_at;
  // Cada estado tiene un texto completo y uno corto para pantallas angostas: nunca se corta a la mitad.
  let state = 'offline'; let text = 'Sin conexión'; let short = 'Sin conexión';
  // Si el último /api/status salió de la caché del service worker, se informa la edad del dato guardado.
  const cachedAt = storage.get('cached-at');
  const age = cachedAge();
  if (age) text = `Sin conexión · datos de ${age}`;
  if (store.get('online') && status && !cachedAt) {
    // El servidor manda: /api/status trae `freshness` con la regla de los 30 minutos ya aplicada.
    // El cálculo local queda solo como respaldo de un servidor viejo en caché.
    const fresh = status.freshness;
    const stale = fresh ? Boolean(fresh.stale) : minutesSince(lastIngest) > 30;
    const ageMin = fresh?.age_seconds != null ? Math.round(fresh.age_seconds / 60) : Math.round(minutesSince(lastIngest));
    state = stale ? 'stale' : 'live';
    if (lastIngest) {
      const when = ago(lastIngest);
      text = stale ? `Datos de hace ${ageMin} min` : `Actualizado ${when}`;
      short = stale ? `Hace ${ageMin} min` : (when === 'recién' ? 'Al día' : when.charAt(0).toUpperCase() + when.slice(1));
    } else { text = 'Esperando los primeros datos'; short = 'Sin datos aún'; }
    if (status.ingest_mode === 'apagada') { state = 'stale'; text = 'Sin actualización automática'; short = 'Sin actualizar'; }
  }
  pill.dataset.state = state;
  pill.setAttribute('aria-live', 'polite');  // que el cambio de estado se anuncie, no solo se pinte
  $('#live-text').textContent = text;
  $('#live-short').textContent = short;
  pill.title = (state === 'stale' ? 'Los datos satelitales están atrasados: puede faltar un foco reciente. ' : '')
    + (newest ? `Último punto de calor visto: ${ago(newest)}. Toca para ver de dónde vienen los datos.` : 'Aún no hay puntos de calor guardados');
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
  setupSheet();
  ['#settings-btn', '#settings-btn-m'].forEach((sel) => $(sel)?.addEventListener('click', openSettings));
  document.addEventListener('brasa:theme', (e) => { if (e.detail !== store.get('theme')) { applyTheme(e.detail); setTheme(e.detail); } });
  $('#emergency-btn')?.addEventListener('click', openEmergency);
  $('#live-pill')?.addEventListener('click', () => { location.hash = '#/calidad'; });
  window.addEventListener('online', () => { store.set('online', true); refreshStatus(); });
  window.addEventListener('offline', () => {
    store.set('online', false);
    updateLivePill();
    const age = cachedAge();
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
  const whenVisible = (fn) => () => { if (!document.hidden) fn(); };
  setInterval(whenVisible(refreshObservations), 120000);
  setInterval(whenVisible(refreshStatus), 60000);
  setInterval(whenVisible(updateLivePill), 30000);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    refreshStatus();
    refreshObservations();
    updateLivePill();
  });
  registerServiceWorker(() => toast('Hay una versión nueva de BRASA.', 'info', 60000, { label: 'Actualizar', onClick: () => location.reload() }));
}

main().catch((err) => {
  // Un error de arranque no debe dejar la pantalla vacía: los números de emergencia siempre quedan a mano.
  console.error(err);
  toast('Algo falló al abrir BRASA. Recarga la página. En una emergencia llama al 130 o al 132.', 'error', 15000);
});
