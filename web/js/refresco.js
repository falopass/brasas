/* «Actualizar» manual del mapa: control propio en la columna derecha de MapLibre, bajo
 * «Mi ubicación», con la edad del dato en una mini píldora debajo. Módulo diferido
 * (initMap lo pide con import()): el arranque ya está al tope del presupuesto de peso. */
import { store } from './store.js';
import { ago, minutesSince, toast } from './util.js';

/** «Actualizado hace X» con la marca del último lote (data_as_of = última ingesta) o,
 *  si la frescura va atrasada, «Sin datos nuevos hace X» con la edad de la fuente más
 *  atrasada (el criterio con que la píldora la nombra, FUEGO-08). Sin `freshness`
 *  (servidor viejo) queda el respaldo de los 30 minutos. */
export function frescuraObs({ status, dataAsOf, now = Date.now() }) {
  const min = minutesSince(dataAsOf, now);
  const fresh = status?.freshness;
  // Sin marca legible: «sin datos nuevos» solo si la frescura ya declaró atraso; sin
  // ella (todavía conectando) es el «esperando los primeros datos» de la píldora.
  if (!Number.isFinite(min)) return fresh?.stale ? 'Sin datos nuevos' : 'Sin datos aún';
  const stale = fresh ? Boolean(fresh.stale) : min > 30;
  if (!stale) return `Actualizado ${ago(dataAsOf, now)}`;
  const viejas = Object.values(fresh?.products ?? {}).filter((f) => f.stale && f.age_seconds != null).map((f) => f.age_seconds);
  return `Sin datos nuevos ${viejas.length ? ago(new Date(now - Math.max(...viejas) * 1000).toISOString(), now) : ago(dataAsOf, now)}`;
}

let corriendo = false;

function pintar(edad) {
  if (!corriendo) edad.textContent = frescuraObs({ status: store.get('status'), dataAsOf: store.get('dataAsOf') });
}

/** Una vuelta de sondeo inmediato. El botón se deshabilita mientras corre (sin solicitudes
 *  duplicadas) y la píldora dice «Actualizando…»; si falla, avisa con toast. Las funciones
 *  de sondeo no lanzan: ordenan su error en el store y aquí se lee. */
async function refrescarTodo(btn, edad) {
  if (corriendo) return;
  corriendo = true;
  btn.disabled = true;
  btn.setAttribute('aria-busy', 'true');
  edad.textContent = 'Actualizando…';
  // app.js es el módulo de entrada y ya está evaluado: este import no descarga nada.
  const { refreshObservations, refreshStatus } = await import('./app.js');
  await Promise.all([refreshObservations(), refreshStatus()]);
  corriendo = false;
  btn.disabled = false;
  btn.removeAttribute('aria-busy');
  const err = store.get('statusError') || store.get('obsError');
  if (err) toast(`No se pudo actualizar: ${err.message}`, 'error');
  pintar(edad);
}

/** El control en el mapa y la edad al día con los sondeos (status y data_as_of cambian
 *  con cada vuelta: no hace falta un reloj propio). */
export function montar(map) {
  const ctrl = document.createElement('div');
  ctrl.className = 'maplibregl-ctrl map-refresh';
  ctrl.innerHTML = `<div class="maplibregl-ctrl-group"><button type="button" id="refresh-btn" title="Actualizar los datos ahora" aria-label="Actualizar los datos ahora"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg></button></div><div class="refresh-age" id="refresh-age" role="status"></div>`;
  const btn = ctrl.querySelector('button');
  const edad = ctrl.querySelector('.refresh-age');
  btn.addEventListener('click', () => refrescarTodo(btn, edad));
  store.on('dataAsOf', () => pintar(edad));
  store.on('status', () => pintar(edad));
  map.addControl({ onAdd: () => ctrl, onRemove: () => ctrl.remove() }, 'top-right');
  pintar(edad);
}
