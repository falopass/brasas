/* BRASA · pantalla pública: parseo puro de ?comunas= y ?rotar= (rotación entre
 * comunas). Sin DOM ni estado global: recibe el query string y devuelve los
 * parámetros listos para resolveComuna (web/js/pantalla.js) y los segundos de
 * rotación. Probado en tests/js/pantalla-rotacion.test.mjs. */

const SEGUNDOS_DEF = 45;
/* Piso técnico de 5 s (la verificación del modo rota con ?rotar=5). Para que una
 * pantalla municipal dé tiempo de leerse, lo razonable es 25 s o más. */
const SEGUNDOS_MIN = 5;
const SEGUNDOS_MAX = 300;

/* Tope de la lista (24 × 45 s ya son 18 min de ciclo); lo descartado queda en `recortadas`. */
const MAX_COMUNAS = 24;

/* Nombre comparable: minúsculas, sin tildes y con espacios simples (como backend/geo.py: _fold). */
const fold = (s) => s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim().replace(/\s+/g, ' ');

const CODIGO = /^\d{5}$/;

/* parseRotation(search, resolver?) → { params, segundos, recortadas }
 * params: trozos de ?comunas= sin vacíos ni duplicados (fold; códigos por código),
 * con tope de MAX_COMUNAS. segundos: ?rotar= en [5, 300]; inválido cae a 45.
 * resolver(trozo) → código|null, opcional: con él «13101» y «Puente Alto» cuentan
 * una sola vez; sin él se deduplica por el texto, como siempre. */
export function parseRotation(search, resolver) {
  const query = new URLSearchParams(typeof search === 'string' ? search : '');
  const seen = new Set();
  const params = [];
  let recortadas = 0;
  for (const trozo of (query.get('comunas') ?? '').split(',')) {
    const p = trozo.trim();
    const resuelto = resolver?.(p);
    const key = resuelto != null ? `c${resuelto}` : CODIGO.test(p) ? `c${p}` : fold(p);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    if (params.length >= MAX_COMUNAS) { recortadas++; continue; }
    params.push(p);
  }
  const n = Number(query.get('rotar'));
  const segundos = Number.isFinite(n) && n > 0
    ? Math.min(Math.max(Math.round(n), SEGUNDOS_MIN), SEGUNDOS_MAX)
    : SEGUNDOS_DEF;
  return { params, segundos, recortadas };
}

export { fold, MAX_COMUNAS };
