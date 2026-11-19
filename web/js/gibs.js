/* Capas raster de NASA GIBS (MAPA-180): teselas WMTS/XYZ gratuitas, sin clave, en
 * EPSG:3857. Lógica pura, sin DOM: la vista arma las URL y map.js las monta.
 *
 * GIBS sirve cada capa en UN solo TileMatrixSet `GoogleMapsCompatible_LevelN`
 * (N = zoom máximo); pedir otro devuelve 400. Verificado contra
 * gibs.earthdata.nasa.gov el 19-11-2026:
 *   GOES-East_ABI_GeoColor ......... Level7  (PNG, cada ~10 min, ~40 min de retraso)
 *   VIIRS_NOAA20_CorrectedReflectance_TrueColor  Level9 (JPEG, diaria)
 *   MODIS_Terra_Aerosol ............. Level6  (PNG, diaria, AOD)
 * El tiempo es `default` (última escena disponible) o `YYYY-MM-DD` (día UTC) en
 * las diarias; en GeoColor cualquier hora pasada con granulo (cada 10 min) y
 * `default` para la última. Un día sin cobertura devuelve 404: la tesela no se
 * dibuja y el resto sigue — nunca se inventa una escena. */

export const GIBS_HOST = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best';
export const GIBS_ATTRIBUTION = 'Imagery provided by NASA\'s Global Imagery Browse Services (GIBS), part of NASA EOSDIS · <a href="https://gibs.earthdata.nasa.gov" target="_blank" rel="noopener">gibs.earthdata.nasa.gov</a>';

// Capas del mapa en vivo (panel «Capas», grupo Contexto).
export const GIBS = {
  goes: {
    key: 'goes', layer: 'GOES-East_ABI_GeoColor', matrix: 'GoogleMapsCompatible_Level7',
    maxzoom: 7, ext: 'png', tipo: 'subdiaria', tiempo: 'default', opacidad: 0.75,
    nombre: 'GOES-19 · color real', corto: 'color real cada ~10 min',
  },
  viirs: {
    key: 'viirs', layer: 'VIIRS_NOAA20_CorrectedReflectance_TrueColor', matrix: 'GoogleMapsCompatible_Level9',
    maxzoom: 9, ext: 'jpg', tipo: 'diaria', tiempo: 'ayer', opacidad: 0.75,
    nombre: 'VIIRS NOAA-20 · color real', corto: 'color real del día',
  },
  aod: {
    key: 'aod', layer: 'MODIS_Terra_Aerosol', matrix: 'GoogleMapsCompatible_Level6',
    maxzoom: 6, ext: 'png', tipo: 'diaria', tiempo: 'ayer', opacidad: 0.65,
    nombre: 'Aerosoles (AOD)', corto: 'aerosol del día',
  },
};

/* Capas de color real para la fecha histórica de un caso (casos.js): el archivo
 * diario retrocede más que NOAA-20. VIIRS S-NPP cubre desde 2015-11-24 y MODIS
 * Aqua desde 2002-07-03 (mismo corte que usa satelite.js para Worldview). */
export const GIBS_HIST = {
  viirs: { layer: 'VIIRS_SNPP_CorrectedReflectance_TrueColor', matrix: 'GoogleMapsCompatible_Level9', maxzoom: 9, ext: 'jpg', desde: '2015-11-24', nombre: 'VIIRS S-NPP' },
  modis: { layer: 'MODIS_Aqua_CorrectedReflectance_TrueColor', matrix: 'GoogleMapsCompatible_Level9', maxzoom: 9, ext: 'jpg', desde: '2002-07-03', nombre: 'MODIS Aqua' },
};
const VIIRS_DESDE_MS = Date.parse('2015-11-24T00:00:00Z');
const MODIS_DESDE_MS = Date.parse('2002-07-03T00:00:00Z');
const DIA_MS = 24 * 3600 * 1000;

/** URL de teselas para MapLibre: `{z}/{y}/{x}` en el orden TileMatrix/TileRow/TileCol
 *  de WMTS (la fila es {y} y la columna {x}, igual que los demás raster del repo). */
export function gibsTileUrl(def, time) {
  return [`${GIBS_HOST}/${def.layer}/default/${time}/${def.matrix}/{z}/{y}/{x}.${def.ext}`];
}

/** Día UTC `YYYY-MM-DD` de una fecha; `ayer` resta un día. Devuelve null si no es fecha. */
export function fechaGibs(dia, ahora = new Date()) {
  const t = ahora instanceof Date ? ahora.getTime() : Date.parse(ahora);
  if (!Number.isFinite(t)) return null;
  const d = dia === 'ayer' ? t - DIA_MS : t;
  return new Date(d).toISOString().slice(0, 10);
}

/** La fecha que pide una capa diaria con el selector «Hoy / Ayer»; las subdiarias
 *  (GeoColor) siempre usan `default`, la última pasada. */
export function tiempoGibs(def, dia, ahora = new Date()) {
  if (def.tipo !== 'diaria') return def.tiempo;
  return fechaGibs(dia === 'hoy' ? 'hoy' : 'ayer', ahora) || def.tiempo;
}

/** Escena histórica para casos.js: `{ key, date, def }` con la capa de color real
 *  que cubre el día del caso, o null si la fecha no es válida o aún no tiene
 *  cobertura (los casos del catálogo son todos ≥ 2017, así que MODIS Aqua cubre). */
export function escenaCaso(startUtc, ahora = Date.now()) {
  const t = Date.parse(String(startUtc ?? ''));
  if (!Number.isFinite(t) || ahora - t < DIA_MS) return null;
  const key = t >= VIIRS_DESDE_MS ? 'viirs' : 'modis';
  const def = GIBS_HIST[key];
  if (t < (key === 'viirs' ? VIIRS_DESDE_MS : MODIS_DESDE_MS)) return null;
  const date = new Date(t).toISOString().slice(0, 10);
  return { key, date, def, nombre: def.nombre };
}
