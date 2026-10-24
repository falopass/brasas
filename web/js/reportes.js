/* «¿Qué pasó con mi reporte?»: estado de los reportes enviados desde este dispositivo (ALR-16).
   Funciones puras, sin DOM: el bloque «Tus reportes anteriores» del formulario lo arma ui.js. */
import { ago, fmtNum, haversineKm, parseUTC, storage } from './util.js';

export const STATUS = { no_verificado: 'En revisión', verificado: 'Verificado', descartado: 'Descartado' };

// Prefijo de reports.EXPIRED_NOTE (backend): distingue un descarte por vencimiento de uno decidido
// por el moderador. Se compara por prefijo, no por igualdad exacta: el texto exacto es del servidor.
const EXPIRED_PREFIX = 'Caducó sin revisar';

/** True cuando el reporte fue descartado porque nadie lo revisó dentro de su ventana. */
export const caducado = (report) =>
  report?.status === 'descartado' && String(report?.moderator_note || '').startsWith(EXPIRED_PREFIX);

/** Los `n` reportes más recientes (el servidor ya los devuelve del más nuevo al más viejo). */
export const latest = (reports, n = 5) => (Array.isArray(reports) ? reports.slice(0, n) : []);

/** «N vecinos lo vieron»: el primer aviso más cada corroboración de otro dispositivo.
 *  Solo se muestra con al menos dos testigos y con la aclaración de que no es verificación
 *  oficial — la palabra la tienen SENAPRED y CONAF. */
export const testigos = (report) => {
  const n = 1 + (Number(report?.corroboraciones) || 0);
  return n >= 2 ? `${n} vecinos lo vieron · no es una verificación oficial` : '';
};

/** Texto de una fila: «Humo visible · hace 3 h · Talca · En revisión», más la nota si la hay.
 *  El lugar es la comuna o las coordenadas tal como llegan (el servidor ya las redondea a ~100 m). */
export function line(report, now = Date.now()) {
  if (!report) return '';
  const where = report.comuna
    || (Number.isFinite(report.lat) && Number.isFinite(report.lon) ? `${report.lat}, ${report.lon}` : null);
  const head = [report.kind_label || 'Reporte', ago(report.created_at, now), where].filter(Boolean).join(' · ');
  const status = STATUS[report.status] || report.status;
  return `${head} · ${status}${report.moderator_note ? `. ${report.moderator_note}` : ''}`;
}

// ------------------------------------------------------------------ qué ya hay cerca del punto
/* Antes de enviar, el formulario muestra lo que BRASA ya sabe del punto (REP-01): avisos de
   otros vecinos —el nuevo reporte se sumaría como testigo, no como reporte suelto— y puntos
   de calor del satélite. Funciones puras y sin DOM: ui.js pide los datos en segundo plano y
   arma el bloque; si la consulta falla o llega tarde, el bloque queda oculto y el envío
   sigue igual. */

// Un foco más viejo o más lejano ya no describe lo que el vecino está viendo ahora.
export const FOCOS_HORAS = 24;
export const FOCOS_KM = 3;

/** Puntos a menos de `km` del lugar, del más nuevo al más viejo y con su distancia en `km`.
 *  Sirve para reportes (`created_at`) y para puntos de calor (`observed_at`). */
export function cercanos(reports, lat, lon, km = 2) {
  if (!Array.isArray(reports) || !Number.isFinite(lat) || !Number.isFinite(lon)) return [];
  const t = (r) => parseUTC(r.created_at || r.observed_at).getTime() || 0;
  return reports
    .filter((r) => r && Number.isFinite(r.lat) && Number.isFinite(r.lon))
    .map((r) => ({ ...r, km: haversineKm(lat, lon, r.lat, r.lon) }))
    .filter((r) => r.km <= km)
    .sort((a, b) => t(b) - t(a));
}

/** «a 700 m» / «a 1,2 km». Bajo 1 km se redondea a centenas: las coordenadas públicas ya
 *  vienen redondeadas a ~100 m y el GPS rural no promete más. */
export function distancia(km) {
  if (!Number.isFinite(km) || km < 0) return '';
  if (km < 1) {
    const m = Math.max(100, Math.round(km * 10) * 100);
    return m < 1000 ? `a ${m} m` : 'a 1 km';
  }
  return `a ${fmtNum(km, km < 10 ? 1 : 0)} km`;
}

const KIND_WORD = { humo: 'humo', llamas: 'llamas', quema: 'una quema o fogata', otro: 'algo' };

/** Resumen de una línea para el bloque: «Un vecino reportó humo a 700 m hace 40 min
 *  (en revisión)»; con varios, «2 vecinos reportaron cerca (1 verificado); el más reciente: …». */
export function resumenCercanos(reports, lat, lon, now = Date.now()) {
  const rows = cercanos(reports, lat, lon);
  if (!rows.length) return '';
  const first = rows[0];
  const what = KIND_WORD[first.kind] || String(first.kind_label || 'algo').toLowerCase();
  const where = first.comuna ? ` en ${first.comuna}` : '';
  const when = ago(first.created_at, now);
  if (rows.length === 1) {
    return `Un vecino reportó ${what} ${distancia(first.km)}${where} ${when} (${(STATUS[first.status] || 'En revisión').toLowerCase()})`;
  }
  const verificados = rows.filter((r) => r.status === 'verificado').length;
  const estado = verificados ? (verificados === 1 ? '1 verificado' : `${verificados} verificados`) : 'en revisión';
  return `${rows.length} vecinos reportaron cerca (${estado}); el más reciente: ${what} ${distancia(first.km)}${where} ${when}`;
}

/** Contexto satelital de una línea: «El satélite vio 2 puntos de calor cerca en las últimas
 *  24 h (el más reciente a 800 m hace 1 h)». '' si no hay puntos dentro del radio. */
export function resumenFocos(points, lat, lon, now = Date.now()) {
  const rows = cercanos(points, lat, lon, FOCOS_KM);
  if (!rows.length) return '';
  const first = rows[0];
  const n = rows.length === 1 ? 'un punto de calor' : `${rows.length} puntos de calor`;
  return `El satélite vio ${n} cerca en las últimas ${FOCOS_HORAS} h (el más reciente ${distancia(first.km)} ${ago(first.observed_at, now)})`;
}

// ------------------------------------------------------------------ cola «sin conexión»
/* Un reporte hecho sin señal queda en el teléfono (brasa:outbox) y ui.js lo reenvía al volver la
   conexión. Solo texto y ubicación: una foto no cabe en localStorage y el formulario lo advierte.
   La clave lleva el prefijo brasa:* para que «Borrar todos mis datos» también la alcance.
   El tope existe porque localStorage es chico; al alcanzarlo se descarta el más viejo y ahora
   `guardar` lo informa en `descartados`: un reporte botado no se puede recuperar y el vecino
   tiene que saber que su texto y su ubicación se perdieron. */

const OUTBOX_MAX = 5;
const OUTBOX_TTL = 24 * 60 * 60 * 1000; // 24 h: un aviso más viejo ya no sirve para una emergencia

const outboxRead = () => {
  const list = storage.get('outbox', []);
  return Array.isArray(list) ? list : [];
};
const outboxWrite = (list) => storage.set('outbox', list);
const outboxQuitar = (id) => outboxWrite(outboxRead().filter((e) => e.id !== id));

/** Agrega un reporte a la cola ({kind, lat, lon, description}). Si se supera el tope sale la
 *  más vieja. Devuelve los datos del ítem guardado (id, created_at, etc.) en el nivel de arriba
 *  —más `item` y `descartados`: la lista de lo que salió por el tope ({id, kind, created_at}),
 *  para que la vista pueda avisar qué se perdió. */
export function guardar(entry) {
  const item = {
    id: entry.id || (globalThis.crypto?.randomUUID?.() ?? `q${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`),
    created_at: new Date().toISOString(),
    ...entry,
  };
  const list = outboxRead().filter((e) => e.id !== item.id);
  list.push(item);
  const descartados = list.splice(0, Math.max(0, list.length - OUTBOX_MAX))
    .map(({ id, kind, created_at }) => ({ id, kind, created_at }));
  outboxWrite(list);
  return { ...item, item, descartados };
}

/** Las que aún sirven para reenviar (menos de 24 h), de la más vieja a la más nueva.
 *  Las vencidas salen de la cola al consultar. */
export function pendientes(now = Date.now()) {
  const all = outboxRead();
  const fresh = all.filter((e) => now - parseUTC(e.created_at).getTime() < OUTBOX_TTL);
  if (fresh.length !== all.length) outboxWrite(fresh);
  return fresh;
}

/** Saca una entrada de la cola. */
export const descartar = outboxQuitar;
/** El servidor ya la recibió (201 nueva o 200 duplicada): sale de la cola igual que un descarte,
 *  pero con otro nombre para que el llamado diga por qué. */
export const marcarEnviado = outboxQuitar;
