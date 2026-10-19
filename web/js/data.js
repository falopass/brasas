/* Datos compartidos de observaciones: una sola forma de pedirlas y una sola forma de filtrarlas. */
import { api } from './api.js';
import { store } from './store.js';

const RELIABLE = ['alta', 'nominal', 'media'];
export const isReliable = (o) => RELIABLE.includes(o.confidence);

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
  return data;
}

/* Solo para las pruebas: la suite lo llama en su setUp para aislar cada caso. */
export function resetObservationCache() {
  lastKey = null;
}

/** Observaciones según los filtros del usuario (sensores y «ocultar los dudosos»). */
export function visibleObservations() {
  const f = store.get('obsFilter');
  return (store.get('observations') || []).filter((o) => f.sensors[o.sensor] !== false && (!f.reliable || isReliable(o)));
}
