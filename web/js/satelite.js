/* Enlaces a visores satelitales externos: módulo puro, sin DOM. Cada función
 * devuelve la URL lista para abrir en otra pestaña, o null si faltan datos.
 * Regla: un visor se ofrece solo si puede mostrar la escena de ese caso.
 *
 * NASA Worldview — parámetros de URL según la documentación oficial
 * (github.com/nasa-gibs/worldview, doc/url_parameters.md):
 *   v = minX,minY,maxX,maxY · extensión del visor en grados (oeste,sur,este,norte)
 *   t = YYYY-MM-DD-Thh:mm:ssZ · día y hora UTC seleccionados
 *   l = capas activas por id de la configuración
 * Capa de reflectancia corregida (config/wv.json de Worldview): VIIRS SNPP tiene
 * datos desde 2015-11-24; para casos anteriores se usa MODIS Aqua (desde
 * 2002-07-03), que pasa sobre Chile a media tarde.
 *
 * SLIDER (RAMMB/CIRA): ?sat=goes-NN&sec=full_disk · «sat» elige el satélite y
 * «sec» el sector; Chile solo aparece en el disco completo. */

const WV = 'https://worldview.earthdata.nasa.gov/';
const SLIDER = 'https://slider.cira.colostate.edu/';
const VIIRS_START = '2015-11-24';
const MODIS_START_MS = Date.parse('2002-07-03'); // MODIS Aqua, la capa usada antes de VIIRS
const DAY_MS = 24 * 3600 * 1000;
const LAYERS = { viirs: 'VIIRS_SNPP_CorrectedReflectance_TrueColor', modis: 'MODIS_Aqua_CorrectedReflectance_TrueColor' };

const validDate = (s) => typeof s === 'string' && !Number.isNaN(Date.parse(s));
const round3 = (n) => Math.round(n * 1000) / 1000;

/** Hay reflectancia corregida para esa fecha: desde MODIS Aqua (2002-07-03) y con ~24 h de latencia. */
export function hayImagen(start, ahora = Date.now()) {
  const t = Date.parse(String(start ?? ''));
  return t >= MODIS_START_MS && ahora - t >= DAY_MS;
}

/** SLIDER muestra el bucle en vivo, no el archivo: solo sirve si el caso terminó hace menos de 48 h. */
export function esReciente(fin, ahora = Date.now()) {
  const t = Date.parse(String(fin ?? ''));
  return Number.isFinite(t) && ahora - t <= 2 * DAY_MS;
}

/** Capa de reflectancia corregida con datos para la fecha de inicio del caso. */
export function worldviewLayer(start) {
  return validDate(start) && start >= VIIRS_START ? LAYERS.viirs : LAYERS.modis;
}

/** URL de NASA Worldview sobre el área del caso, con la imagen del día que empezó. */
export function worldviewUrl({ bbox, start, end, ahora = Date.now() } = {}) {
  if (!Array.isArray(bbox) || bbox.length !== 4 || !bbox.every((n) => Number.isFinite(n))) return null;
  if (!validDate(start) || !validDate(end) || !hayImagen(start, ahora)) return null;
  const iso = new Date(start).toISOString(); // 2024-02-02T12:00:00.000Z
  const t = `${iso.slice(0, 10)}-T${iso.slice(11, 19)}Z`;
  return `${WV}?v=${bbox.map(round3).join(',')}&t=${encodeURIComponent(t)}&l=${worldviewLayer(start)}`;
}

/** URL del visor SLIDER de GOES (RAMMB/CIRA) en el sector de disco completo. */
export function sliderUrl({ satellite, end, ahora = Date.now() } = {}) {
  const m = /(\d{2})/.exec(String(satellite ?? ''));
  return m && esReciente(end, ahora) ? `${SLIDER}?sat=goes-${m[1]}&sec=full_disk` : null;
}
