/* «¿Qué pasó con mi reporte?»: estado de los reportes enviados desde este dispositivo (ALR-16).
   Funciones puras, sin DOM: el bloque «Tus reportes anteriores» del formulario lo arma ui.js. */
import { ago } from './util.js';

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
