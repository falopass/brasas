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
  { key: 'senapred', url: 'senapred', label: 'Alertas de SENAPRED', aria: 'Mostrar las comunas con alerta oficial de SENAPRED', on: false },
  { key: 'scars', url: 'cicatrices', label: 'Cicatrices de la temporada', aria: 'Mostrar las cicatrices de la temporada', on: false },
  { key: 'reports', url: 'avisos', label: 'Avisos de vecinos', aria: 'Mostrar los avisos de vecinos', on: true },
  { key: 'places', url: 'lugares', label: 'Mis lugares', aria: 'Mostrar mis lugares', on: true },
  { key: 'hulls', url: 'huellas', label: 'Huellas de calor', aria: 'Mostrar las huellas de calor', on: false },
  { key: 'lightning', url: 'rayos', label: 'Rayos de la última hora', aria: 'Mostrar los rayos de la última hora', on: false },
  { key: 'viento', url: 'viento', label: 'Viento', aria: 'Mostrar el viento estimado a 10 m', on: false },
  { key: 'relieve', url: 'relieve', label: 'Relieve', aria: 'Mostrar el relieve sombreado', on: false },
];

// Capas excluyentes: dos coropletas sobre las mismas comunas se taparían entre sí — el
// peligro, la lluvia y las alertas de SENAPRED pintan el mismo polígono comunal, y la lluvia
// (contexto del combustible) no debe leerse como el peligro ni como una alerta vigente.
const EXCLUYE = { risk: ['rain', 'senapred'], rain: ['risk', 'senapred'], senapred: ['risk', 'rain'] };

/** Estado nuevo con `key` prendida/apagada, respetando exclusiones (risk ↔ rain ↔ senapred). */
export function toggleCapa(state, key, on) {
  const next = { ...state, [key]: Boolean(on) };
  if (on) for (const otra of EXCLUYE[key] || []) next[otra] = false;
  return next;
}

/** `#/mapa?capas=focos,riesgo` → las capas del control, prendidas solo las listadas.
 *  null si el parámetro no viene (la vista usa sus valores por defecto). `capas=` vacío
 *  apaga todas: así una vista con todo apagado también se puede compartir. Los nombres
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

// Gravedad de una alerta SENAPRED para la coropleta (OFI-207): si una comuna aparece en
// varias alertas vigentes, la pinta la más grave que la nombra.
const SENAPRED_ORDEN = { roja: 3, amarilla: 2, temprana_preventiva: 1, otra: 0 };

/** Alertas de `GET /api/senapred/alertas` → `{ tipos, porComuna }`:
 *  `tipos` es `{code: tipo}` con la clase más grave que nombra cada comuna (para el
 *  feature-state y la trama del mapa) y `porComuna` es `{code: [alertas]}` (para el popup).
 *  Las alertas que no nombran territorio (`comunas` vacía) no pintan ni se consultan. */
export function senapredPorComuna(alerts) {
  const tipos = {};
  const porComuna = {};
  for (const a of alerts || []) {
    const tipo = SENAPRED_ORDEN[a?.tipo] !== undefined ? a.tipo : 'otra';
    for (const code of a?.comunas || []) {
      if (!(code in tipos) || SENAPRED_ORDEN[tipo] > SENAPRED_ORDEN[tipos[code]]) tipos[code] = tipo;
      (porComuna[code] ||= []).push(a);
    }
  }
  return { tipos, porComuna };
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

/* Prioridad al resolver un toque sobre el mapa (MAPA-157): gana el número menor.
 * `celda` es un punto de `detections` con `count > 1`; lo no listado queda en 9,
 * detrás de todo lo que abre una ficha. */
export const PRIORIDAD_TOQUE = {
  official: 0, reports: 0, 'official-labels': 0,
  detections: 1, lightning: 1, services: 1, places: 1,
  celda: 2, 'incident-rings': 2,
  'goes-pixels': 3,
  'incident-labels': 4, 'incident-hulls-line': 4,
  'scars-fill': 4, 'incident-hulls-fill': 4,
  'risk-fill': 5, 'rain-fill': 5, 'senapred-fill': 5,
};

/** Elige el candidato que gana un toque: primero prioridad, luego menor
 *  `distPx`; al empate total gana el primero de la lista. Función pura. */
export function elegirObjetivo(candidatos) {
  if (!candidatos?.length) return null;
  const prioridad = (c) => PRIORIDAD_TOQUE[c.capa === 'detections' && c.feature?.properties?.count > 1 ? 'celda' : c.capa] ?? 9;
  return candidatos.reduce((mejor, c) => (prioridad(c) - prioridad(mejor) || c.distPx - mejor.distPx) < 0 ? c : mejor);
}

/** Enlace profundo de «Compartir» (MAPA-165): `foco=` y `conaf=` vuelan al punto y
 *  abren su ficha al montar el mapa; `incidente` apunta a su página. `origen` es
 *  location.origin; ojo: el parámetro `lat` lleva la latitud. Función pura. */
export function enlaceCompartir(tipo, item, origen = '') {
  const base = String(origen || '');
  const pos = `lat=${item.lat}&lon=${item.lon}&z=12`;
  const id = encodeURIComponent(item.id);
  if (tipo === 'foco') return `${base}/#/mapa?${pos}&foco=${id}`;
  if (tipo === 'incidente') return `${base}/#/incendio/${id}`;
  if (tipo === 'conaf') return `${base}/#/mapa?${pos}&conaf=${id}`;
  return `${base}/#/mapa`;
}
