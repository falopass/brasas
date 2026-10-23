/* Mantenimiento de la casa (PREP-03): las tareas que se repiten cada temporada caducan.
 * Módulo puro, sin DOM: la vista guarda en localStorage el día en que se hizo cada una
 * (`check:casa:fechas`, solo en ese dispositivo) y aquí se decide si sigue «al día» o ya
 * «toca» de nuevo. Cada `fuente` es una clave del diccionario SRC de views/preparate.js
 * (CONT-05): las mismas recomendaciones de la casa preparada, con su caducidad. */

import { utcDate } from './formato.js';

export const MANTENIMIENTO = [
  { clave: 'zona', texto: 'Despejé la franja alrededor de la casa: sin leña, pasto seco ni material que pueda arder.', meses: 6, fuente: 'casaConaf' },
  { clave: 'techo', texto: 'Limpié el techo y las canaletas de hojas, ramas y basura seca.', meses: 12, fuente: 'casaConaf' },
  { clave: 'pasto', texto: 'Corté el pasto seco y retiré matorrales en un radio de 10 a 30 m, según el terreno.', meses: 3, fuente: 'casaConaf' },
  { clave: 'lena', texto: 'Leña, gas y combustibles siguen guardados a al menos 10 m de la casa.', meses: 6, fuente: 'casaConaf' },
  { clave: 'agua', texto: 'Revisé que la manguera alcanza todo el perímetro y que la fuente de agua funciona.', meses: 6, fuente: 'casaConaf' },
];

/* Acepta ISO o Date; cualquier valor ilegible da null, nunca lanza. */
const asDate = (v) => {
  const d = v instanceof Date ? v : utcDate(v);
  return d && Number.isFinite(d.getTime()) ? d : null;
};

/** Días completos entre `fecha` y `hoy` (ISO o Date). Null si falta o no se lee alguno. */
export function diasDesde(fecha, hoy = new Date()) {
  const d = asDate(fecha); const h = asDate(hoy);
  if (!d || !h) return null;
  return Math.floor((h.getTime() - d.getTime()) / 86400000);
}

/** ¿La tarea ya venció? `fecha` + `meses` meses de calendario (UTC) comparado con `hoy`.
 *  Devuelve true/false, o null si la fecha no es válida: null nunca revienta. */
export function vence(fechaISO, meses, hoy = new Date()) {
  const d = asDate(fechaISO); const h = asDate(hoy);
  if (!d || !h || !Number.isFinite(meses)) return null;
  const limite = new Date(Date.UTC(
    d.getUTCFullYear(), d.getUTCMonth() + meses, d.getUTCDate(),
    d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds(), d.getUTCMilliseconds(),
  ));
  return h.getTime() >= limite.getTime();
}

/** 'sin-registrar' | 'al-dia' | 'toca' */
export function estadoTarea(fechaISO, meses, hoy = new Date()) {
  if (!asDate(fechaISO)) return 'sin-registrar';
  return vence(fechaISO, meses, hoy) ? 'toca' : 'al-dia';
}
