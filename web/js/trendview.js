/* Comparador de riesgo semana a semana: el pronóstico de hoy contra el que BRASA emitió
 * siete días antes para el mismo día (`/api/risk/{code}/trend`). Funciones puras, sin DOM
 * ni fetch: la ficha de la comuna las usa para dibujar el bloque «¿Y la semana pasada?».
 * Todo habla de pronósticos: lo que cambia es la expectativa, nunca «va a haber un incendio». */
import { RISK } from './util.js';

const levelName = (level) => RISK[level]?.label.toLowerCase();

const joinList = (parts) => (parts.length > 1 ? `${parts.slice(0, -1).join(', ')} y ${parts.at(-1)}` : parts.join(''));

const capitalize = (text) => (text ? text[0].toUpperCase() + text.slice(1) : text);

const MISSING_LABELS = {
  hoy: 'Hoy no hay pronóstico para ese día',
  semana_pasada: 'No hay pronóstico de la semana pasada para ese día',
  ambos: 'No hay pronóstico ni de hoy ni de la semana pasada',
};

/* Tono del cambio con las clases que ya existen: `status-badge` naranja si sube (alerta),
 * verde si baja (calma) y la placa base gris si sigue igual; `muted` cuando no se compara. */
const TONES = { sube: 'st-riesgo', baja: 'st-tranquilo', igual: '', sin_anterior: 'muted' };
export const tone = (change) => TONES[change] ?? '';

/** Encabezado del bloque: «Esta semana 3 días suben y falta el pronóstico de hoy en 2 días».
 *  Si no hay comparaciones, nombra qué falta; con un resumen vacío devuelve ''. */
export function headline(summary) {
  const s = summary || {};
  const sinHoy = s.sin_hoy || 0;
  const sinSemana = Math.max(0, (s.sin_anterior || 0) - sinHoy);
  const parts = [];
  if (s.sube) parts.push(s.sube === 1 ? '1 día sube' : `${s.sube} días suben`);
  if (s.baja) parts.push(s.baja === 1 ? '1 día baja' : `${s.baja} días bajan`);
  if (s.igual) parts.push(s.igual === 1 ? '1 día sigue igual' : `${s.igual} días siguen igual`);
  if (sinHoy) parts.push(sinHoy === 1 ? 'falta el pronóstico de hoy en 1 día' : `falta el pronóstico de hoy en ${sinHoy} días`);
  if (sinSemana) parts.push(sinSemana === 1 ? '1 no tiene con qué compararse' : `${sinSemana} no tienen con qué compararse`);
  if (!parts.length) return '';
  if (!s.sube && !s.baja && !s.igual) {
    return sinHoy ? capitalize(joinList(parts)) : 'Sin pronóstico de la semana pasada para comparar';
  }
  return `Esta semana ${joinList(parts)}`;
}

/** Texto de una fila: los dos niveles comparados y el `change_label` que manda el servidor.
 *  `sin_anterior` no se compara: avisa cuál de los dos pronósticos falta. */
export function line(row) {
  if (!row) return '';
  const label = row.change_label || MISSING_LABELS[row.missing] || 'Sin pronóstico de la semana pasada para ese día';
  if (row.change === 'sin_anterior') return label;
  const cur = levelName(row.current); const prev = levelName(row.previous);
  if (!cur || !prev) return label;
  return cur === prev ? `${cur} · ${label}` : `${prev} → ${cur} · ${label}`;
}
