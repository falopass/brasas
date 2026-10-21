/* Capas del mapa principal (MAPA-01): qué se prende y apaga desde el control flotante,
 * cómo se refleja en la URL (#/mapa?capas=focos,riesgo) y cómo se agrupan los focos por
 * celda cuando el zoom está lejos. Lógica pura, sin DOM: la vista la aplica al mapa. */

// Orden fijo del control y del parámetro `capas` (el mismo que siguen los switches del
// panel lateral). `key` es el nombre interno (estado y capas MapLibre vía applyLayers);
// `url` es el nombre público en la URL compartible.
export const CAPAS = [
  { key: 'focos', url: 'focos', label: 'Focos de calor', aria: 'Mostrar los focos de calor', on: true },
  { key: 'incendios', url: 'incendios', label: 'Incendios de CONAF', aria: 'Mostrar los incendios que informa CONAF', on: true },
  { key: 'risk', url: 'riesgo', label: 'Peligro de incendio', aria: 'Mostrar el peligro de incendio por comuna', on: false },
  { key: 'aire', url: 'aire', label: 'Humo en el aire', aria: 'Mostrar el humo que ve el satélite GOES', on: false },
  { key: 'rain', url: 'lluvia', label: 'Lluvia de la temporada', aria: 'Mostrar la lluvia de la temporada', on: false },
  { key: 'scars', url: 'cicatrices', label: 'Cicatrices de la temporada', aria: 'Mostrar las cicatrices de la temporada', on: false },
  { key: 'reports', url: 'avisos', label: 'Avisos de vecinos', aria: 'Mostrar los avisos de vecinos', on: true },
  { key: 'places', url: 'lugares', label: 'Mis lugares', aria: 'Mostrar mis lugares', on: true },
  { key: 'hulls', url: 'huellas', label: 'Huellas de calor', aria: 'Mostrar las huellas de calor', on: false },
  { key: 'lightning', url: 'rayos', label: 'Rayos de la última hora', aria: 'Mostrar los rayos de la última hora', on: false },
];

// Capas excluyentes: dos coropletas sobre las mismas comunas se taparían entre sí, y la
// lluvia (contexto del combustible) no debe leerse como el peligro de hoy.
const EXCLUYE = { risk: 'rain', rain: 'risk' };

/** Estado nuevo con `key` prendida/apagada, respetando exclusiones (risk ↔ rain). */
export function toggleCapa(state, key, on) {
  const next = { ...state, [key]: Boolean(on) };
  if (on && EXCLUYE[key]) next[EXCLUYE[key]] = false;
  return next;
}

/** `#/mapa?capas=focos,riesgo` → las diez capas, prendidas solo las listadas.
 *  null si el parámetro no viene (la vista usa sus valores por defecto). `capas=` vacío
 *  apaga las diez: así una vista con todo apagado también se puede compartir. Los nombres
 *  de los enlaces viejos (focos, incendios, riesgo, aire) valen lo mismo de siempre. */
export function capasFromUrl(raw) {
  if (raw === undefined || raw === null) return null;
  const active = new Set(String(raw).split(',').map((s) => s.trim()).filter(Boolean));
  return Object.fromEntries(CAPAS.map((c) => [c.key, active.has(c.url)]));
}

/** Estado → texto del parámetro, solo las activas en el orden del control. */
export function capasToUrl(state) {
  return CAPAS.filter((c) => state[c.key]).map((c) => c.url).join(',');
}

// Desde este zoom cada detección se dibuja sola; por debajo se agrupan por celda.
export const CELL_ZOOM_MAX = 7;
const CELL_PX = 56; // lado de la celda en pantalla: agrupa lo que se ve como un mismo punto

/** Agrupa puntos GeoJSON en celdas de ~56 px al zoom dado. Cada celda queda en el
 *  centroide de sus miembros con `count` y hereda el dato más urgente (menor edad,
 *  mayor FRP, alguno confiable) para que la rampa de color siga contando lo mismo.
 *  A `CELL_ZOOM_MAX` o más devuelve la colección intacta (sin copia). */
export function decimatePoints(fc, zoom) {
  if (!fc?.features?.length || zoom >= CELL_ZOOM_MAX) return fc;
  const cell = (360 * (CELL_PX / 256)) / 2 ** zoom; // grados que cubre la celda a este zoom
  const cells = new Map();
  for (const f of fc.features) {
    const [lon, lat] = f.geometry.coordinates;
    const key = `${Math.floor(lon / cell)}:${Math.floor(lat / cell)}`;
    const g = cells.get(key);
    if (!g) { cells.set(key, { n: 1, lon, lat, f, age_h: f.properties.age_h ?? Infinity, frp_mw: f.properties.frp_mw ?? 0, reliable: f.properties.reliable === true }); continue; }
    g.n += 1; g.lon += lon; g.lat += lat;
    g.age_h = Math.min(g.age_h, f.properties.age_h ?? Infinity);
    g.frp_mw = Math.max(g.frp_mw, f.properties.frp_mw ?? 0);
    g.reliable = g.reliable || f.properties.reliable === true;
  }
  const features = [...cells.values()].map((g) => (g.n === 1 ? g.f : {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [g.lon / g.n, g.lat / g.n] },
    properties: { count: g.n, age_h: g.age_h === Infinity ? 0 : g.age_h, frp_mw: g.frp_mw, reliable: g.reliable, sensor: 'CELDA' },
  }));
  return { type: 'FeatureCollection', features };
}
