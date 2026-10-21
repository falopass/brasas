/* Fechas y números en formato chileno: única fuente. Sin DOM, así que también la usan las
 * páginas livianas (lite, pantalla, respuesta) y los tests con node:test; la app la consume
 * reexportada desde util.js. Chile cambia de offset dos veces al año (UTC-3/UTC-4): el
 * huso horario se declara una sola vez aquí. */

export const TZ = 'America/Santiago';
const nf = (digits) => new Intl.NumberFormat('es-CL', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
export const fmtNum = (n, digits = 0) => (Number.isFinite(n) ? nf(digits).format(n) : '—');

/** Sin zona en la cadena se asume UTC; con `Z` o un desfase (`+03:00`, `-03:00`) se respeta. */
export const parseUTC = (s) => {
  const text = typeof s === 'string' ? s : '';
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/.test(text) ? text : `${text}Z`);
};
/** La fecha o null: una cadena ilegible nunca llega a la interfaz ni lanza. */
export const utcDate = (iso) => {
  const date = parseUTC(iso);
  return Number.isNaN(date.getTime()) ? null : date;
};
export const fmtTime = (iso) => utcDate(iso)?.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ }) ?? '—';
export const fmtDateTime = (iso, opts = {}) => utcDate(iso)?.toLocaleString('es-CL', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ, ...opts }) ?? 'sin datos';

/** "hace 12 min", "hace 3 h", "hace 2 días" — unidades completas (floor): la edad mostrada nunca
 * adelanta la real; un foco de 89 min dice «hace 1 h», no «hace 2 h» ni «hace 1.5 h». */
export function ago(iso, now = Date.now()) {
  const date = utcDate(iso);
  if (!date) return 'sin datos';
  const minutes = Math.floor((now - date.getTime()) / 60000);
  if (minutes < 1) return 'recién';
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `hace ${hours} h`;
  return `hace ${Math.floor(hours / 24)} días`;
}
