/* Humo visto por GOES-19 (DET-16 / DET-48): manchas de aerosol de la última hora, del producto
 * ABI-L2-ADPF enriquecidas de día con espesor óptico ABI-L2-AODF. Es una detección de humo del
 * satélite: no es un incendio ni su trayectoria. */

// Gris ceniza por tema, tenue: va bajo los focos de calor y no se confunde con ellos.
export const SMOKE_COLOR = { dark: '#a89f92', light: '#6e675c' };
export const SMOKE_OPACITY = 0.25;

// Paleta cualitativa por espesor óptico (DET-48): ceniza tenue → ceniza-ámbar → ocre-humo,
// siempre apagada para distinguirse de los focos de calor rojos/naranjas.
export const SMOKE_DENSITY_COLOR = {
  dark: { tenue: '#a89f92', moderado: '#b69b74', denso: '#a67c46' },
  light: { tenue: '#6e675c', moderado: '#7b6546', denso: '#6b4c24' },
};
export const SMOKE_DENSITY_OPACITY = { tenue: 0.22, moderado: 0.34, denso: 0.48 };

/** Expresión MapLibre para el color de relleno según `density` (con respaldo a `SMOKE_COLOR`). */
export function smokeFillColorExpr(theme = 'dark') {
  const key = SMOKE_DENSITY_COLOR[theme] ? theme : 'dark';
  const pal = SMOKE_DENSITY_COLOR[key];
  return [
    'match',
    ['get', 'density'],
    'tenue', pal.tenue,
    'moderado', pal.moderado,
    'denso', pal.denso,
    SMOKE_COLOR[key],
  ];
}

/** Expresión MapLibre para la opacidad según `density` (con respaldo a `SMOKE_OPACITY`). */
export function smokeFillOpacityExpr() {
  return [
    'match',
    ['get', 'density'],
    'tenue', SMOKE_DENSITY_OPACITY.tenue,
    'moderado', SMOKE_DENSITY_OPACITY.moderado,
    'denso', SMOKE_DENSITY_OPACITY.denso,
    SMOKE_OPACITY,
  ];
}

/** Resume cuántos polígonos de humo traen cada densidad cualitativa de AODF. */
export function smokeDensitySummary(fc) {
  let tenue = 0;
  let moderado = 0;
  let denso = 0;
  let sinAod = 0;
  const features = Array.isArray(fc?.features) ? fc.features : [];
  for (const f of features) {
    const d = f?.properties?.density;
    if (d === 'tenue') tenue += 1;
    else if (d === 'moderado') moderado += 1;
    else if (d === 'denso') denso += 1;
    else sinAod += 1;
  }
  return { hasAod: (tenue + moderado + denso) > 0, tenue, moderado, denso, sinAod };
}

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
