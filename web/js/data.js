/* Datos compartidos de observaciones: una sola forma de pedirlas y una sola forma de filtrarlas. */
import { api } from './api.js';
import { store } from './store.js';

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

const FILTRO_BASE = { reliable: false, sensors: { ABI: true, VIIRS: true, MODIS: true } };

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
