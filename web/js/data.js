/* Datos compartidos de observaciones: una sola forma de pedirlas y una sola forma de filtrarlas. */
import { api } from './api.js';
import { store } from './store.js';

const RELIABLE = ['alta', 'nominal', 'media'];
export const isReliable = (o) => RELIABLE.includes(o.confidence);

let seq = 0;
/** Pide las observaciones de la ventana actual. Gana la última solicitud: una respuesta vieja no pisa una nueva. */
export async function loadObservations() {
  const mine = ++seq;
  const data = await api.observations(store.get('obsHours'), false);
  if (mine !== seq) return null;
  store.set('dataAsOf', data.data_as_of);
  return data;
}

/** Observaciones según los filtros del usuario (sensores y «ocultar los dudosos»). */
export function visibleObservations() {
  const f = store.get('obsFilter');
  return (store.get('observations') || []).filter((o) => f.sensors[o.sensor] !== false && (!f.reliable || isReliable(o)));
}
