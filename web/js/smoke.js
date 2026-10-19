/* Capa de humo GOES-19 (DET-04): se importa bajo demanda desde el interruptor del
 * mapa, para no engordar el arranque. El conjunto abierto devuelve los polígonos de
 * aerosol del producto ABI-L2-ADPF de la última hora; no son incendios ni trayectorias. */

// Gris ceniza con poca tinta (el mismo que pinta «smoke-fill» en map.js): se ve bajo
// los focos sin leerse como peligro ni como incendio.
export const SMOKE_COLORS = { dark: '#bdb6aa', light: '#6f675c' };

/** Polígonos de humo de la última hora, normalizados a FeatureCollection.
 *  El endpoint responde application/geo+json, que api.js no parsea: va fetch directo. */
export async function loadSmoke() {
  const res = await fetch('/api/opendata/smoke.geojson?hours=1').catch(() => null);
  if (!res?.ok) throw new Error('El humo de GOES no está disponible ahora');
  const data = await res.json().catch(() => null);
  if (data?.type !== 'FeatureCollection' || !Array.isArray(data.features)) {
    throw new Error('Respuesta de humo inválida.');
  }
  return { type: 'FeatureCollection', features: data.features };
}
