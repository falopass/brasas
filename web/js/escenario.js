/* El escenario estimado de propagación en palabras que entienda un vecino.
 * Módulo puro: sin DOM y sin imports. Solo traduce el objeto `spread` del API
 * (backend/fwi.py, propagation_scenario) sin agregar física ni inventar condiciones.
 * El rótulo de «no es una predicción» no vive aquí: lo pone el API en `note`. */

/** Los ocho rumbos de la ficha (web/js/util.js, `cardinal`): se repiten para no importar nada. */
const CARDINALS = ['norte', 'noreste', 'este', 'sureste', 'sur', 'suroeste', 'oeste', 'noroeste'];

/** Cortes de FFMC (humedad del combustible fino) donde cambia la frase de `humedad()`.
 *  Desde `muySeco` el combustible está muy seco; desde `seco`, seco; bajo `seco`, conserva humedad. */
export const FFMC_TRAMOS = { muySeco: 90, seco: 80 };

const cardinal = (deg) => CARDINALS[Math.round((((deg % 360) + 360) % 360) / 45) % 8];
const num = (n, digits) => new Intl.NumberFormat('es-CL', { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(n);
const mayus = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/** `true` solo para el escenario que calcula BRASA; cualquier otra cosa no pinta el bloque. */
export const esEscenario = (spread) => spread?.kind === 'escenario_estimado';

/** «hacia el sur», o `''` si el API no trae rumbo: nunca se inventa uno. */
export const direccion = (spread) => (Number.isFinite(spread?.direction_deg) ? `hacia el ${cardinal(spread.direction_deg)}` : '');

/** «viento de 24 km/h desde el noroeste», o `''` sin velocidad y dirección del viento. */
export const viento = (spread) => (Number.isFinite(spread?.wind_kmh) && Number.isFinite(spread?.wind_deg)
  ? `viento de ${num(spread.wind_kmh, 0)} km/h desde el ${cardinal(spread.wind_deg)}`
  : '');

/** Qué tan seco está el combustible fino, según el FFMC. Sin FFMC devuelve `''`. */
export function humedad(spread) {
  const ffmc = spread?.ffmc;
  if (!Number.isFinite(ffmc)) return '';
  if (ffmc >= FFMC_TRAMOS.muySeco) return 'los pastos y la hojarasca están muy secos: cualquier chispa prende';
  if (ffmc >= FFMC_TRAMOS.seco) return 'los pastos y la hojarasca están secos: el fuego puede prender con facilidad';
  return 'los pastos y la hojarasca todavía conservan humedad: cuesta más que prendan';
}

/** Lo que el escenario NO considera, en palabras: pendiente, escala del clima y combate. */
export function limites(spread) {
  const out = [];
  if (spread?.slope_deg == null) {
    out.push('Terreno plano: la pendiente sale del modelo de elevación Copernicus GLO-90 cuando está disponible; sin ese dato no se considera, y una ladera empinada puede acelerar el avance.');
  }
  out.push('El viento y la humedad del combustible son los del centro de la comuna, no los del punto exacto del fuego.');
  out.push('No incluye el trabajo de los equipos de extinción: el combate puede frenar o detener el avance.');
  return out;
}

/** La línea técnica que antes iba inline, para el `<details>` de la ficha. */
function detalle(spread) {
  const ros = Number.isFinite(spread?.speed_m_min) ? `ROS estimada ${num(spread.speed_m_min, 1)} m/min` : '';
  const kmh = Number.isFinite(spread?.speed_kmh) ? `${num(spread.speed_kmh, 1)} km/h` : '';
  const rumbo = Number.isFinite(spread?.direction_deg) ? `hacia ${Math.round(spread.direction_deg)}°` : '';
  const isi = Number.isFinite(spread?.isi) ? `ISI efectivo ${num(spread.isi, 1)}` : '';
  return [ros && kmh ? `${ros} (${kmh})` : ros || kmh, rumbo, isi, spread?.fuel, spread?.reference].filter(Boolean).join(' · ');
}

/** `{ titular, detalle, limites[] }` listo para pintar, o `null` si no es un escenario de BRASA. */
export function resumen(spread) {
  if (!esEscenario(spread)) return null;
  const avance = Number.isFinite(spread.speed_kmh)
    ? ['el fuego podría avanzar unos', `${num(spread.speed_kmh, 1)} km/h`, direccion(spread)].filter(Boolean).join(' ')
    : '';
  const aire = viento(spread);
  const clima = avance ? (aire ? `${avance}, con ${aire}` : avance) : (aire ? `hay ${aire}` : '');
  const hum = humedad(spread);
  const titular = clima
    ? `Con el clima de ahora ${clima}${hum ? `, y ${hum}` : ''}.`
    : (hum ? `${mayus(hum)}.` : 'No hay datos suficientes para estimar el avance del fuego.');
  return { titular, detalle: detalle(spread), limites: limites(spread) };
}
