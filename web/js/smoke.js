/* Humo visto por GOES-19 (DET-16): manchas de aerosol de la última hora, del producto
 * ABI-L2-ADPF. Es una detección de humo del satélite: no es un incendio ni su trayectoria. */

// Gris ceniza por tema, tenue: va bajo los focos de calor y no se confunde con ellos.
export const SMOKE_COLOR = { dark: '#a89f92', light: '#6e675c' };
export const SMOKE_OPACITY = 0.25;

/** Polígonos de humo de la última hora (`hours=1`: cada hora son ~6 archivos de ~1 MB
 *  en el servidor; no pedir más por defecto). Lanza un error corto si no responde 200. */
export async function loadSmoke() {
  const res = await fetch('/api/opendata/smoke.geojson?hours=1');
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(typeof body?.detail === 'string' ? body.detail
      : `El humo de GOES no está disponible ahora (error ${res.status}).`);
  }
  if (body?.type !== 'FeatureCollection' || !Array.isArray(body.features)) {
    throw new Error('El humo de GOES no está disponible ahora.');
  }
  return body;
}
