/* «¿Qué pasó con mi reporte?»: estado de los reportes enviados desde este dispositivo (ALR-16).
   Funciones puras, sin DOM: el bloque «Tus reportes anteriores» del formulario lo arma ui.js. */
import { ago, parseUTC, storage } from './util.js';

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

// ------------------------------------------------------------------ cola «sin conexión»
/* Un reporte hecho sin señal queda en el teléfono (brasa:outbox) y ui.js lo reenvía al volver la
   conexión. Solo texto y ubicación: una foto no cabe en localStorage y el formulario lo advierte.
   La clave lleva el prefijo brasa:* para que «Borrar todos mis datos» también la alcance. */

const OUTBOX_MAX = 5;
const OUTBOX_TTL = 24 * 60 * 60 * 1000; // 24 h: un aviso más viejo ya no sirve para una emergencia

const outboxRead = () => {
  const list = storage.get('outbox', []);
  return Array.isArray(list) ? list : [];
};
const outboxWrite = (list) => storage.set('outbox', list);
const outboxQuitar = (id) => outboxWrite(outboxRead().filter((e) => e.id !== id));

/** Agrega un reporte a la cola ({kind, lat, lon, description}) y devuelve la entrada guardada.
 *  Si se supera el tope, sale la más vieja. */
export function guardar(entry) {
  const item = {
    id: entry.id || (globalThis.crypto?.randomUUID?.() ?? `q${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`),
    created_at: new Date().toISOString(),
    ...entry,
  };
  const list = outboxRead().filter((e) => e.id !== item.id);
  list.push(item);
  while (list.length > OUTBOX_MAX) list.shift();
  outboxWrite(list);
  return item;
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
