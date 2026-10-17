/* BRASA Chile — arranque de la aplicación: rutas, navegación, tema, datos compartidos y hoja móvil. */
import { api } from './api.js';
import { detectionsGeoJSON, initMap, onReady, placesGeoJSON, setData, setTheme } from './map.js';
import { registerServiceWorker } from './push.js';
import { store } from './store.js';
import { openEmergency } from './ui.js';
import { $, ago, minutesSince, storage, toast } from './util.js';
import zona from './views/zona.js';
import mapa from './views/mapa.js';
import riesgo from './views/riesgo.js';
import casos from './views/casos.js';
import preparate from './views/preparate.js';

const ICONS = {
  'mi-zona': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21Z"/><circle cx="12" cy="10" r="2.4"/></svg>',
  mapa: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4Z"/><path d="M9 4v14M15 6v14"/></svg>',
  riesgo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 14.8V5a2 2 0 1 0-4 0v9.8a4 4 0 1 0 4 0Z"/><path d="M12 9v7"/></svg>',
  casos: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
  preparate: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.2 7.5 9.5 4.3-1.3 7.5-4.9 7.5-9.5V6L12 3Z"/><path d="m9 12 2 2 4-4"/></svg>',
};
const VIEWS = [zona, mapa, riesgo, casos, preparate];
const LABELS = { 'mi-zona': 'Mi zona', mapa: 'Mapa', riesgo: 'Riesgo', casos: 'Casos', preparate: 'Prepárate' };
let current = null;

function renderNav() {
  // Íconos y etiquetas son constantes de este archivo (contenido confiable).
  const markup = VIEWS.map((v) => `<a class="nav-link" href="#/${v.id}" data-view="${v.id}">
    <span aria-hidden="true">${ICONS[v.id]}</span><small>${LABELS[v.id]}</small></a>`).join('');
  $('#nav').innerHTML = markup;
  $('#tabbar').innerHTML = markup;
}

function parseRoute() {
  const [path, query = ''] = location.hash.replace(/^#\/?/, '').split('?');
  const [view = 'mi-zona', ...rest] = path.split('/');
  return { view: VIEWS.some((v) => v.id === view) ? view : 'mi-zona', rest, params: Object.fromEntries(new URLSearchParams(query)) };
}

async function route() {
  const { view, rest, params } = parseRoute();
  const next = VIEWS.find((v) => v.id === view);
  document.querySelectorAll('.nav-link').forEach((a) => { if (a.dataset.view !== view) a.removeAttribute('aria-current'); else a.setAttribute('aria-current', 'page'); });
  if (current && current !== next) current.unmount?.();
  const container = $('#view');
  if (current !== next) { container.replaceChildren(); container.scrollTop = 0; }
  current = next;
  store.set('view', view);
  document.title = `${LABELS[view]} · BRASA Chile`;
  setSheet(next.sheet || 'half');
  await next.mount(container, { rest, params });
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
    const data = await api.observations(store.get('obsHours'), false);
    store.set('observations', data.points);
    store.set('dataAsOf', data.data_as_of);
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

function updateLivePill() {
  const pill = $('#live-pill');
  const status = store.get('status');
  const newest = status ? Object.values(status.newest_observation || {}).sort().pop() : null;
  const lastIngest = status?.last_ingest_at;
  let state = 'offline'; let text = 'Sin conexión';
  if (store.get('online') && status) {
    const age = minutesSince(lastIngest);
    state = age <= 30 ? 'live' : 'stale';
    text = lastIngest ? `Actualizado ${ago(lastIngest)}` : 'Esperando la primera ingesta';
    if (!status.scheduler_enabled) { state = 'stale'; text = 'Ingesta automática apagada'; }
  }
  pill.dataset.state = state;
  $('#live-text').textContent = text;
  pill.title = newest ? `Detección más reciente: ${ago(newest)}` : 'Aún no hay detecciones guardadas';
}

function visibleObservations() {
  const f = store.get('obsFilter');
  return (store.get('observations') || []).filter((o) => f.sensors[o.sensor] !== false
    && (!f.reliable || ['alta', 'nominal', 'media'].includes(o.confidence)));
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
  applyTheme(document.documentElement.dataset.theme || 'dark');
  setupSheet();
  $('#theme-toggle').addEventListener('click', () => { applyTheme(store.get('theme') === 'dark' ? 'light' : 'dark'); setTheme(store.get('theme')); });
  $('#emergency-btn').innerHTML = '<span aria-hidden="true">☎</span> <span class="lbl">Emergencias</span>';
  $('#emergency-btn').addEventListener('click', openEmergency);
  $('#live-pill').addEventListener('click', () => { location.hash = '#/mapa?panel=fuentes'; });
  window.addEventListener('online', () => { store.set('online', true); refreshStatus(); });
  window.addEventListener('offline', () => { store.set('online', false); updateLivePill(); toast('Sin conexión: se muestran los últimos datos guardados.', 'error'); });

  try {
    store.set('config', await api.config());
  } catch (err) {
    toast(`No se pudo conectar con el servidor de BRASA: ${err.message}`, 'error', 8000);
  }
  if (!window.maplibregl) {
    $('#map').innerHTML = '<p class="empty">No se pudo cargar el motor del mapa.</p>';
  } else {
    initMap($('#map'));
    // Índice liviano de comunas para buscadores (nombre, región, centro).
    fetch('/web/data/comunas.geojson').then((r) => r.json()).then((fc) => {
      store.set('comunasIndex', fc.features.map((f) => ({ code: f.properties.code, name: f.properties.name, region: f.properties.region,
        center: f.properties.center, bbox: f.properties.bbox })).sort((a, b) => a.name.localeCompare(b.name, 'es')));
    }).catch(() => {});
  }
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
  setInterval(refreshObservations, 120000);
  setInterval(refreshStatus, 60000);
  setInterval(updateLivePill, 30000);
  registerServiceWorker();
}

main();
