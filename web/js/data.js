/* Datos compartidos de observaciones: una sola forma de pedirlas y una sola forma de filtrarlas. */
import { api } from './api.js';
import { store } from './store.js';
import { haversineKm } from './util.js';

const RELIABLE = ['alta', 'nominal', 'media'];
export const isReliable = (o) => RELIABLE.includes(o?.confidence);
/* En Chile por contrato del servidor: /api/observations conserva un punto si tiene comuna
 * o si pertenece a un incidente con comuna chilena; descartarlo aquí recortaría el borde
 * de un incendio real cuando su comuna no se pudo emparejar. */
const inChile = (o) => o?.comuna_code != null || o?.incident_id != null;

let seq = 0;
let lastKey = null;
/** Pide las observaciones de la ventana actual. Gana la última solicitud: una respuesta vieja no pisa una nueva.
 *  Si el corte es idéntico al último entregado devuelve null: no hay nada nuevo que pintar. */
export async function loadObservations() {
  const mine = ++seq;
  const data = await api.observations(store.get('obsHours'), false);
  if (mine !== seq) return null;
  store.set('dataAsOf', data.data_as_of);
  store.set('obsTruncated', data.truncated ? data.limit : 0);
  const key = `${store.get('obsHours')}|${data.data_as_of}|${data.points.length}|${data.truncated ? 1 : 0}`;
  if (key === lastKey) return null;
  lastKey = key;
  return { ...data, points: data.points.filter(inChile) };
}

/* Solo para las pruebas: la suite lo llama en su setUp para aislar cada caso. */
export function resetObservationCache() {
  lastKey = null;
}

const FILTRO_BASE = { reliable: false, sensors: { ABI: true, VIIRS: true, MODIS: true, LANDSAT: true } };

/** Filtro de focos siempre completo: un estado viejo o guardado a medias devuelve los
 *  valores por defecto en lo que falte, sin tirar la pintada ni vaciar la lista. */
export function normalizarFiltro(f) {
  const sensors = { ...FILTRO_BASE.sensors };
  if (typeof f === 'object' && f !== null) {
    for (const s of Object.keys(sensors)) {
      if (typeof f.sensors?.[s] === 'boolean') sensors[s] = f.sensors[s];
    }
  }
  return { reliable: f?.reliable === true, sensors };
}

/** Observaciones según los filtros del usuario (sensores y «ocultar los dudosos»). */
export function visibleObservations() {
  const f = normalizarFiltro(store.get('obsFilter'));
  const obs = store.get('observations');
  return (Array.isArray(obs) ? obs : []).filter(
    (o) => inChile(o) && f.sensors[o.sensor] !== false && (!f.reliable || isReliable(o)),
  );
}

/** Solo los puntos a `km` o menos del centro {lat, lon} (VIS-03). Pura: sin centro
 *  válido o sin radio devuelve la lista tal cual; los puntos sin lat/lon finitos quedan fuera. */
export function filtrarPorDistancia(points, centro, km) {
  const lista = Array.isArray(points) ? points : [];
  if (!km || !Number.isFinite(centro?.lat) || !Number.isFinite(centro?.lon)) return lista;
  return lista.filter((o) => Number.isFinite(o?.lat) && Number.isFinite(o?.lon) && haversineKm(centro.lat, centro.lon, o.lat, o.lon) <= km);
}

const INCIDENT_STATUS_FUEGO = ['posible', 'reportado', 'confirmado', 'controlado'];

/** Incidentes con evidencia de fuego (no anomalías sueltas ni fuentes fijas), armados
 *  desde las observaciones. Es la regla única del mapa (VIS-03): con radio, un
 *  incidente aparece en la lista «Posibles incendios» y en sus anillos/huellas solo
 *  si tiene un miembro en la lista de puntos entregada; el centro publicado no
 *  cuenta aparte, así lista y mapa muestran siempre el mismo conjunto.
 *  Cada fila conserva la coordenada de su miembro más reciente con lat/lon finitos
 *  (para «a N km», sin depender de /api/incidents) y `vistos` cuenta solo los
 *  miembros presentes, no el total del incidente (`n` se conserva aparte). */
export function fireIncidents(points) {
  const by = new Map();
  for (const o of points || []) {
    if (!o.incident_id || o.incident_fixed || !INCIDENT_STATUS_FUEGO.includes(o.incident_status)) continue;
    const inc = by.get(o.incident_id) || { id: o.incident_id, status: o.incident_status, n: o.incident_n, vistos: 0, last: '', coordAt: '', comuna: o.comuna, region: o.region };
    inc.vistos += 1;
    if (o.observed_at >= inc.last) inc.last = o.observed_at;
    if (Number.isFinite(o.lat) && Number.isFinite(o.lon) && o.observed_at >= inc.coordAt) { inc.coordAt = o.observed_at; inc.lat = o.lat; inc.lon = o.lon; }
    by.set(o.incident_id, inc);
  }
  return [...by.values()].sort((a, b) => (a.last < b.last ? 1 : -1));
}

const plain = (s) => String(s ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();

/** Busca una comuna por nombre sin exigir tildes ni mayúsculas («quilpue» encuentra «Quilpué»).
 *  Devuelve { exact, matches }: `exact` es la comuna de nombre idéntico al texto; `matches` hasta 8
 *  candidatas: primero las que empiezan con el texto, después las que lo contienen, por nombre. */
export function findComuna(list, text) {
  const q = plain(text);
  if (!q) return { exact: null, matches: [] };
  const starts = [];
  const contains = [];
  for (const c of list || []) {
    const n = plain(c.name);
    if (n.startsWith(q)) starts.push(c);
    else if (n.includes(q)) contains.push(c);
  }
  const byName = (a, b) => a.name.localeCompare(b.name, 'es');
  starts.sort(byName);
  contains.sort(byName);
  return { exact: starts.find((c) => plain(c.name) === q) || null, matches: [...starts, ...contains].slice(0, 8) };
}
