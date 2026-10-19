/* Enlaces a visores satelitales externos: módulo puro, sin DOM. Cada función
 * devuelve la URL lista para abrir en otra pestaña, o null si faltan datos.
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
const LAYERS = { viirs: 'VIIRS_SNPP_CorrectedReflectance_TrueColor', modis: 'MODIS_Aqua_CorrectedReflectance_TrueColor' };

const validDate = (s) => typeof s === 'string' && !Number.isNaN(Date.parse(s));
const round3 = (n) => Math.round(n * 1000) / 1000;

/** Capa de reflectancia corregida con datos para la fecha de inicio del caso. */
export function worldviewLayer(start) {
  return validDate(start) && start >= VIIRS_START ? LAYERS.viirs : LAYERS.modis;
}

/** URL de NASA Worldview sobre el área del caso, con la imagen del día que empezó. */
export function worldviewUrl({ bbox, start, end } = {}) {
  if (!Array.isArray(bbox) || bbox.length !== 4 || !bbox.every((n) => Number.isFinite(n))) return null;
  if (!validDate(start) || !validDate(end)) return null;
  const iso = new Date(start).toISOString(); // 2024-02-02T12:00:00.000Z
  const t = `${iso.slice(0, 10)}-T${iso.slice(11, 19)}Z`;
  return `${WV}?v=${bbox.map(round3).join(',')}&t=${encodeURIComponent(t)}&l=${worldviewLayer(start)}`;
}

/** URL del visor SLIDER de GOES (RAMMB/CIRA) en el sector de disco completo. */
export function sliderUrl({ satellite } = {}) {
  const m = /(\d{2})/.exec(String(satellite ?? ''));
  return m ? `${SLIDER}?sat=goes-${m[1]}&sec=full_disk` : null;
}
