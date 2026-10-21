/* La píldora de la cabecera (PILDORA-01): distingue tres cosas que antes se veían iguales:
 * «este teléfono no tiene señal», «el servidor de BRASA no responde» y «el servidor
 * responde pero los datos están viejos». Módulo puro, sin DOM: app.js le pasa el estado
 * del store y pinta lo que devuelve. */
import { ago, minutesSince } from './util.js';

// Errores que sí significan «este teléfono no tiene señal»: api.js los marca con estos códigos.
const SIN_SENAL = new Set(['OFFLINE', 'TIMEOUT']);

/* Edad del /api/status que sirvió la caché del service worker («hace 5 min», «hace 2 h») o null. */
export function cachedAge(cachedAt, now = Date.now()) {
  const min = minutesSince(cachedAt, now);
  if (!Number.isFinite(min)) return null;
  return min < 60 ? `hace ${Math.round(min)} min` : ago(cachedAt, now);
}

/** Estado, textos y título de la píldora según lo último que se sabe del servidor.
 * online: navigator.onLine; statusError: el ApiError del último /api/status (o null);
 * status: el último estado bueno (o null); cachedAt: fecha del dato que sirvió el SW. */
export function pillState({ online, statusError, status, cachedAt, now = Date.now() }) {
  const newest = status ? Object.values(status.newest_observation || {}).sort().pop() : null;
  const lastIngest = status?.last_ingest_at;
  // Cada estado tiene un texto completo y uno corto para pantallas angostas: nunca se corta a la mitad.
  let state; let text; let short;
  if (online === false || SIN_SENAL.has(statusError?.code)) {
    // La falla es del lado del teléfono: sin señal o la solicitud no llegó a salir.
    state = 'offline'; text = 'Sin conexión'; short = 'Sin conexión';
    const age = cachedAge(cachedAt, now);
    if (age) text = `Sin conexión · datos de ${age}`;
  } else if (statusError) {
    // La red sí llegó y el servidor devolvió error (5xx u otro): el que falla es BRASA.
    state = 'servidor'; text = 'BRASA no responde · reintentando'; short = 'Reintentando';
  } else if (status && cachedAt) {
    // El service worker sirvió un estado guardado: no hubo contacto fresco con el servidor.
    state = 'offline'; text = 'Sin conexión'; short = 'Sin conexión';
    const age = cachedAge(cachedAt, now);
    if (age) text = `Sin conexión · datos de ${age}`;
  } else if (status) {
    // El servidor manda: /api/status trae `freshness` con la regla de los 30 minutos ya aplicada.
    // El cálculo local queda solo como respaldo de un servidor viejo en caché.
    const fresh = status.freshness;
    const stale = fresh ? Boolean(fresh.stale) : minutesSince(lastIngest, now) > 30;
    const ageMin = fresh?.age_seconds != null ? Math.round(fresh.age_seconds / 60) : Math.round(minutesSince(lastIngest, now));
    state = stale ? 'stale' : 'live';
    if (lastIngest) {
      const when = ago(lastIngest, now);
      text = stale ? `Datos de hace ${ageMin} min` : `Actualizado ${when}`;
      short = stale ? `Hace ${ageMin} min` : (when === 'recién' ? 'Al día' : when.charAt(0).toUpperCase() + when.slice(1));
    } else { state = 'sin-datos'; text = 'Esperando los primeros datos'; short = 'Sin datos aún'; }
    if (status.ingest_mode === 'apagada') { state = 'stale'; text = 'Sin actualización automática'; short = 'Sin actualizar'; }
  } else { state = 'sin-datos'; text = 'Esperando los primeros datos'; short = 'Sin datos aún'; }
  const title = (state === 'stale' ? 'Los datos satelitales están atrasados: puede faltar un foco reciente. ' : '')
    + (newest ? `Último punto de calor visto: ${ago(newest, now)}. Toca para ver de dónde vienen los datos.` : 'Aún no hay puntos de calor guardados');
  return { state, text, short, title };
}
