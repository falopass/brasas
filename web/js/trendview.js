/* Comparador de riesgo semana a semana: el pronóstico de hoy contra el que BRASA emitió
 * siete días antes para el mismo día (`/api/risk/{code}/trend`). Funciones puras, sin DOM
 * ni fetch: la ficha de la comuna las usa para dibujar el bloque «¿Y la semana pasada?».
 * Todo habla de pronósticos: lo que cambia es la expectativa, nunca «va a haber un incendio». */
import { RISK } from './util.js';

const levelName = (level) => RISK[level]?.label.toLowerCase();

const joinList = (parts) => (parts.length > 1 ? `${parts.slice(0, -1).join(', ')} y ${parts.at(-1)}` : parts.join(''));

/* Tono del cambio con las clases que ya existen: `status-badge` naranja si sube (alerta),
 * verde si baja (calma) y la placa base gris si sigue igual; `muted` cuando no se compara. */
const TONES = { sube: 'st-riesgo', baja: 'st-tranquilo', igual: '', sin_anterior: 'muted' };
export const tone = (change) => TONES[change] ?? '';

/** Encabezado del bloque: «Esta semana 3 días suben y 2 no tienen con qué compararse».
 *  Sin foto previa lo resume entero; con un resumen vacío devuelve ''. */
export function headline(summary) {
  const s = summary || {};
  if (!s.sube && !s.baja && !s.igual) return s.sin_anterior ? 'Sin pronóstico de la semana pasada para comparar' : '';
  const parts = [];
  if (s.sube) parts.push(s.sube === 1 ? '1 día sube' : `${s.sube} días suben`);
  if (s.baja) parts.push(s.baja === 1 ? '1 día baja' : `${s.baja} días bajan`);
  if (s.igual) parts.push(s.igual === 1 ? '1 día sigue igual' : `${s.igual} días siguen igual`);
  if (s.sin_anterior) parts.push(s.sin_anterior === 1 ? '1 no tiene con qué compararse' : `${s.sin_anterior} no tienen con qué compararse`);
  return `Esta semana ${joinList(parts)}`;
}

/** Texto de una fila: los dos niveles comparados y el `change_label` que manda el servidor.
 *  `sin_anterior` no se compara: solo avisa que falta el pronóstico de hace una semana. */
export function line(row) {
  if (!row) return '';
  const label = row.change_label || 'Sin pronóstico de la semana pasada para ese día';
  if (row.change === 'sin_anterior') return label;
  const cur = levelName(row.current); const prev = levelName(row.previous);
  if (!cur || !prev) return label;
  return cur === prev ? `${cur} · ${label}` : `${prev} → ${cur} · ${label}`;
}
