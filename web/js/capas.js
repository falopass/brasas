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
  { key: 'scars', url: 'cicatrices', label: 'Cicatrices de incendios', aria: 'Mostrar el suelo quemado de grandes incendios y el calor reciente', on: false },
  { key: 'snaspe', url: 'snaspe', label: 'Áreas protegidas (SNASPE)', aria: 'Mostrar los parques y reservas nacionales (SNASPE)', on: false },
  { key: 'reports', url: 'avisos', label: 'Avisos de vecinos', aria: 'Mostrar los avisos de vecinos', on: true },
  { key: 'places', url: 'lugares', label: 'Mis lugares', aria: 'Mostrar mis lugares', on: true },
  { key: 'hulls', url: 'huellas', label: 'Huellas de calor', aria: 'Mostrar las huellas de calor', on: false },
  { key: 'lightning', url: 'rayos', label: 'Rayos de la última hora', aria: 'Mostrar los rayos de la última hora', on: false },
  { key: 'viento', url: 'viento', label: 'Viento', aria: 'Mostrar el viento estimado a 10 m', on: false },
  { key: 'relieve', url: 'relieve', label: 'Relieve', aria: 'Mostrar el relieve sombreado', on: false },
  // MAPA-180: imagen satelital real de NASA GIBS (teselas WMTS, sin clave).
  { key: 'gibs_goes', url: 'goes-color', label: 'GOES · color real', aria: 'Mostrar la imagen GOES de color real, actualizada cada 10 minutos', on: false },
  { key: 'gibs_viirs', url: 'viirs-color', label: 'VIIRS · color real diario', aria: 'Mostrar la imagen VIIRS de color real del día', on: false },
  { key: 'gibs_aod', url: 'aerosol', label: 'Aerosoles (AOD)', aria: 'Mostrar el aerosol del día según MODIS Terra', on: false },
  // OFI-34: capas WMS externas GWIS/EFFIS (Copernicus, CC BY 4.0).
  { key: 'gwis_ranking', url: 'gwis-peligro', label: 'Peligro inusual · GWIS (ECMWF)', aria: 'Mostrar el peligro inusual diario según GWIS y ECMWF (contexto externo)', on: false },
  { key: 'gwis_ba', url: 'gwis-quemado', label: 'Área quemada 30 días · GWIS', aria: 'Mostrar el área quemada de los últimos 30 días según GWIS', on: false },
  // MAPA-185: cobertura terrestre ESA WorldCover 10 m (2021, CC BY 4.0).
  { key: 'worldcover', url: 'cobertura', label: 'Uso de suelo · ESA 10 m', aria: 'Mostrar el uso de suelo ESA WorldCover 2021 a 10 metros', on: false },
  // MAPA-189: terreno 3D nativo en MapLibre (Mapterhorn + respaldo AWS Terrain Tiles).
  { key: 'terreno3d', url: 'terreno3d', label: 'Relieve 3D', aria: 'Mostrar el relieve del terreno en 3D con inclinación', on: false },
  // MAPA-183: zonas de interfaz urbano-forestal (WUI) CONAF GEPRIF (teselas vectoriales ArcGIS).
  { key: 'wui', url: 'interfaz', label: 'Interfaz urbano-forestal · CONAF', aria: 'Mostrar las zonas de interfaz urbano-forestal según CONAF GEPRIF', on: false },
];

// Capas excluyentes: dos coropletas sobre las mismas comunas se taparían entre sí — el
// peligro, la lluvia y las alertas de SENAPRED pintan el mismo polígono comunal, y las
// capas temáticas GWIS se apagan al elegir cualquiera de ellas (y viceversa).
export const COROPLETAS = ['risk', 'rain', 'senapred'];
const TEMATICAS_EXCLUYENTES = ['risk', 'rain', 'senapred', 'gwis_ranking', 'gwis_ba'];
const EXCLUYE = Object.fromEntries(
  TEMATICAS_EXCLUYENTES.map((k) => [k, TEMATICAS_EXCLUYENTES.filter((otra) => otra !== k)]),
);

// Perfiles rápidos del panel de capas (UX-82): a lo sumo una coropleta activa por perfil.
export const PRESETS = [
  { id: 'emergencia', label: 'Emergencia', desc: 'Focos, CONAF, humo y alertas SENAPRED', layers: { focos: true, incendios: true, aire: true, reports: true, places: true, senapred: true } },
  { id: 'prevencion', label: 'Prevención', desc: 'Focos, CONAF, peligro comunal y viento', layers: { focos: true, incendios: true, risk: true, viento: true, places: true } },
  { id: 'satelite', label: 'Satélite hoy', desc: 'Focos, imagen satelital GOES y humo', layers: { focos: true, gibs_goes: true, aire: true, places: true } },
];

/** Estado nuevo con `key` prendida/apagada, respetando exclusiones entre coropletas y GWIS. */
export function toggleCapa(state, key, on) {
  const next = { ...state, [key]: Boolean(on) };
  if (on) for (const otra of EXCLUYE[key] || []) next[otra] = false;
  return next;
}

/** Elige una sola coropleta (o ninguna si `key` es vacío, null, undefined o «ninguna»),
 *  conservando el resto de las capas sin mutar `state` (UX-82). Cuando elige una coropleta
 *  real, apaga también las capas GWIS excluyentes. */
export function seleccionarCoropleta(state, key) {
  const next = { ...state };
  for (const k of COROPLETAS) next[k] = false;
  if (COROPLETAS.includes(key)) {
    next[key] = true;
    next.gwis_ranking = false;
    next.gwis_ba = false;
  }
  return next;
}

/** Aplica un perfil rápido sin mutar `state` (UX-82): «basico» restaura los valores por
 *  defecto de CAPAS; un perfil de PRESETS enciende solo sus capas (con a lo sumo una
 *  coropleta); cualquier otro identificador devuelve una copia sin cambios. */
export function aplicarPreset(state, presetId) {
  if (presetId === 'basico') return Object.fromEntries(CAPAS.map((c) => [c.key, Boolean(c.on)]));
  const preset = PRESETS.find((p) => p.id === presetId);
  if (!preset) return { ...state };
  let next = Object.fromEntries(CAPAS.map((c) => [c.key, false]));
  for (const [k, on] of Object.entries(preset.layers)) {
    if (on) next = toggleCapa(next, k, true);
  }
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
  'snaspe-fill': 6,
};

/** Elige el candidato que gana un toque: primero prioridad, luego menor
 *  `distPx`; al empate total gana el primero de la lista. Función pura. */
export function elegirObjetivo(candidatos) {
  if (!candidatos?.length) return null;
  const prioridad = (c) => PRIORIDAD_TOQUE[c.capa === 'detections' && c.feature?.properties?.count > 1 ? 'celda' : c.capa] ?? 9;
  return candidatos.reduce((mejor, c) => (prioridad(c) - prioridad(mejor) || c.distPx - mejor.distPx) < 0 ? c : mejor);
}

/** Enlace profundo de «Compartir» (MAPA-165): `incidente` y `conaf` salen por /i/, que el
 *  rastreador sí ve (el # nunca llega al servidor) y sirve la tarjeta con la ficha; `foco`
 *  sigue por # porque un punto suelto no tiene tarjeta propia. `origen` es location.origin.
 *  Ojo: el parámetro `lat` lleva la latitud. Función pura. */
export function enlaceCompartir(tipo, item, origen = '') {
  const base = String(origen || '');
  const pos = `lat=${item.lat}&lon=${item.lon}&z=12`;
  const id = encodeURIComponent(item.id);
  if (tipo === 'foco') return `${base}/#/mapa?${pos}&foco=${id}`;
  if (tipo === 'incidente') return `${base}/i/${id}`;
  if (tipo === 'conaf') return `${base}/i/conaf/${id}`;
  return `${base}/#/mapa`;
}
