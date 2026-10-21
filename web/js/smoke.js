/* Humo visto por GOES-19 (DET-16): manchas de aerosol de la última hora, del producto
 * ABI-L2-ADPF. Es una detección de humo del satélite: no es un incendio ni su trayectoria. */

// Gris ceniza por tema, tenue: va bajo los focos de calor y no se confunde con ellos.
export const SMOKE_COLOR = { dark: '#a89f92', light: '#6e675c' };
export const SMOKE_OPACITY = 0.25;

// Mismo tope de 12 s que el cliente común (FIX-43): en señal rural una petición puede
// quedar colgada sin resolverse nunca y la vista se quedaría «cargando» para siempre.
const SMOKE_TIMEOUT_MS = 12_000;

// AbortSignal.timeout donde exista (Safari < 16 no lo trae); si no, AbortController con
// un temporizador que cancel() limpia para no dejarlo vivo tras la respuesta.
function timeoutSignal(ms) {
  if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
    return { signal: AbortSignal.timeout(ms), cancel() {} };
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  return { signal: ctrl.signal, cancel: () => clearTimeout(timer) };
}

/** Polígonos de humo de la última hora (`hours=1`: cada hora son ~6 archivos de ~1 MB
 *  en el servidor; no pedir más por defecto). Lanza un error corto si no responde 200,
 *  si el cuerpo no es GeoJSON o si la señal se cuelga más allá del tope. */
export async function loadSmoke() {
  const { signal, cancel } = timeoutSignal(SMOKE_TIMEOUT_MS);
  let res;
  let body;
  try {
    res = await fetch('/api/opendata/smoke.geojson?hours=1', { signal });
    body = await res.json().catch(() => null);
  } finally {
    cancel();
    if (signal.aborted) {
      throw new Error('El humo de GOES tardó demasiado en responder; revisa la señal y reintenta.');
    }
  }
  if (!res.ok) {
    throw new Error(typeof body?.detail === 'string' ? body.detail
      : `El humo de GOES no está disponible ahora (error ${res.status}).`);
  }
  if (body?.type !== 'FeatureCollection' || !Array.isArray(body.features)) {
    throw new Error('El humo de GOES no está disponible ahora.');
  }
  return body;
}
