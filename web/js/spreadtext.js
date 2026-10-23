/* El «Escenario estimado de avance» en palabras de vecino (FUEGO-14): qué empuja el
 * fuego (el viento), qué tan seco está el pasto fino (el FFMC) y qué no se sabe
 * (la pendiente). Módulo puro, sin DOM ni imports de vistas: compone las frases de
 * escenario.js —la única traducción del `spread` del API— para no repetirlas.
 *
 * Bandas de FFMC (índice de humedad del combustible fino del FWI canadiense): las
 * mismas de escenario.js (FFMC_TRAMOS: muy seco ≥ 90, seco ≥ 80); el número exacto
 * queda para la línea técnica. */

import { direccion, esEscenario, humedad, resumen as resumenEscenario, viento } from './escenario.js';

const num = (n, d) => new Intl.NumberFormat('es-CL', { maximumFractionDigits: d, minimumFractionDigits: 0 }).format(n);
const mayus = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/* La forma correcta del rótulo (guarda QA-79): la negación tiene que ser literal. */
const ETIQUETA = 'Escenario estimado: no es una predicción ni el perímetro del incendio.';

/** Velocidad y rumbo del avance con el viento que lo empuja; nunca «hacia undefined». */
function fraseResumen(spread) {
  const rumbo = direccion(spread);
  const aire = viento(spread);
  const avance = Number.isFinite(spread.speed_kmh) ? `podría avanzar unos ${num(spread.speed_kmh, 1)} km/h` : '';
  if (!avance && !aire) return 'No hay datos suficientes para estimar el avance del fuego.';
  let resumen = mayus(avance ? `${avance}${rumbo ? ` ${rumbo}` : ''}${aire ? `, empujado por ${aire}` : ''}` : `hay ${aire}`);
  if (!Number.isFinite(spread.direction_deg)) resumen += '; no se sabe hacia dónde';
  return `${resumen}.`;
}

/** Las razones en orden: el viento, la sequedad del pasto fino y lo que el escenario no ve. */
function frasesPorque(spread) {
  const frases = [];
  const aire = viento(spread);
  if (aire) frases.push(`Cuanto más fuerte el viento, más rápido avanza el fuego: ${aire}.`);
  else if (Number.isFinite(spread.wind_kmh)) frases.push('El viento es lo que más empuja el fuego, y ahora no se conoce desde dónde sopla.');
  else frases.push('El viento es lo que más empuja el fuego, pero no hay dato de cómo sopla ahora.');
  const hum = humedad(spread);
  if (hum) frases.push(`${mayus(hum)}.`);
  frases.push(spread.slope_deg == null
    ? 'BRASA todavía no tiene modelo de elevación; si el fuego sube una ladera puede ir más rápido. Este escenario supone terreno plano.'
    : 'Este escenario ya considera la pendiente del terreno.');
  return frases.join(' ');
}

/** `{ resumen, porque, tecnico, etiqueta }` listo para la ficha, o null si no es un escenario de BRASA. */
export function spreadWords(spread) {
  if (!esEscenario(spread)) return null;
  return {
    resumen: fraseResumen(spread),
    porque: frasesPorque(spread),
    tecnico: resumenEscenario(spread).detalle,
    etiqueta: ETIQUETA,
  };
}
