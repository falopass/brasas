/* Capas conmutables del mapa (MAPA-01): orden en el control, estado por defecto,
 * exclusividades y el parámetro `capas` de la URL para compartir la vista
 * (#/mapa?capas=focos,riesgo lista solo las capas encendidas). */

// `label` es el texto visible del chip y `desc` lo completa en el nombre accesible:
// «Riesgo, peligro de incendio hoy». La etiqueta siempre contiene el texto visible (axe).
export const LAYERS = [
  { key: 'focos', label: 'Focos', desc: 'puntos de calor satelitales', on: true },
  { key: 'incendios', label: 'Incendios', desc: 'informados por CONAF', on: true },
  { key: 'riesgo', label: 'Riesgo', desc: 'peligro de incendio hoy', on: false, off: 'lluvia' },
  { key: 'lluvia', label: 'Lluvia', desc: 'de la temporada', on: false, off: 'riesgo' },
  { key: 'avisos', label: 'Avisos', desc: 'de vecinos revisados', on: true },
  { key: 'lugares', label: 'Lugares', desc: 'guardados en este dispositivo', on: true },
  { key: 'huellas', label: 'Huellas', desc: 'de calor por incidente abierto', on: false },
  { key: 'rayos', label: 'Rayos', desc: 'de la última hora', on: false },
];
const KEYS = LAYERS.map((l) => l.key);

export const defaultCapas = () => Object.fromEntries(LAYERS.map((l) => [l.key, l.on]));

/** Enciende o apaga `key` en `state` devolviendo un objeto nuevo. Si la capa declara
 *  `off`, al encenderla apaga a la otra (riesgo y lluvia son coropletas sobre las
 *  mismas comunas: juntas se taparían). Clave desconocida: devuelve el mismo estado. */
export function setCapa(state, key, on) {
  const layer = LAYERS.find((l) => l.key === key);
  if (!layer) return state;
  const next = { ...state, [key]: Boolean(on) };
  if (next[key] && layer.off) next[layer.off] = false;
  return next;
}

/** Estado desde el parámetro `capas` de la URL: solo las nombradas quedan encendidas,
 *  aplicadas en el orden de la lista (con excluyentes gana la última). Sin parámetro
 *  devuelve null: la vista conserva sus valores por defecto. */
export function parseCapas(param) {
  if (param == null) return null;
  let state = Object.fromEntries(KEYS.map((k) => [k, false]));
  for (const raw of param.split(',')) state = setCapa(state, raw.trim(), true);
  return state;
}

/** El estado como parámetro `capas`: las encendidas, en el orden del control. */
export function capasParam(state) {
  return KEYS.filter((k) => state[k]).join(',');
}

/** El hash con `capas` al día: conserva la vista y el resto de los parámetros.
 *  La lista va sin codificar para que la URL compartida se lea directo. */
export function hashWithCapas(hash, state) {
  const [rawPath, query = ''] = (hash || '').replace(/^#/, '').split('?');
  // Un hash que no es ruta («#panel» del salto de contenido) se descarta: la base es la vista.
  const path = rawPath.startsWith('/') ? rawPath : '/mapa';
  const params = new URLSearchParams(query);
  params.delete('capas');
  const rest = params.toString();
  return `#${path}?${rest ? `${rest}&` : ''}capas=${capasParam(state)}`;
}
